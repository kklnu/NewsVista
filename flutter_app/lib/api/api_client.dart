import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'models.dart';
import 'news_cache.dart';

/// A readable error for the UI (never raw exception text).
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final bool notFound;

  /// True for connectivity/server-availability problems (not "not found").
  final bool offline;

  const ApiException(this.message, {this.statusCode, this.notFound = false, this.offline = false});

  @override
  String toString() => message;
}

/// Reads stored results from the NewsVista server. It never contacts news
/// feeds or AI providers; collection and AI generation happen on the server.
class ApiClient {
  ApiClient({String? baseUrl, http.Client? client, NewsCache? cache})
      : baseUrl = baseUrl ?? AppConfig.apiBaseUrl,
        _http = client ?? http.Client(),
        _cache = cache ?? NewsCache();

  final String baseUrl;
  final http.Client _http;
  final NewsCache _cache;

  Future<StoryListResponse> fetchStories({
    int limit = AppConfig.pageSize,
    int offset = 0,
    int minPublishers = 1,
    String? category,
    String? query,
  }) async {
    final cacheable = offset == 0 && (query == null || query.trim().isEmpty);
    final key = 'list:$minPublishers:${category ?? 'all'}';
    try {
      final json = await _get('/stories', {
        'limit': '$limit',
        'offset': '$offset',
        'min_publishers': '$minPublishers',
        'category': ?category,
        if (query != null && query.trim().isNotEmpty) 'q': query.trim(),
      });
      if (cacheable) await _cache.save(key, json);
      return StoryListResponse.fromJson(json);
    } on ApiException catch (e) {
      final saved = e.offline && cacheable ? await _cache.load(key) : null;
      if (saved == null) rethrow;
      return StoryListResponse.fromJson(saved.$1, cachedAt: saved.$2);
    }
  }

  Future<StoryDetail> fetchStory(String id) async {
    final key = 'story:$id';
    try {
      final json = await _get('/stories/${Uri.encodeComponent(id)}');
      await _cache.save(key, json);
      return StoryDetail.fromJson(json);
    } on ApiException catch (e) {
      final saved = e.offline ? await _cache.load(key) : null;
      if (saved == null) rethrow;
      return StoryDetail.fromJson(saved.$1, cachedAt: saved.$2);
    }
  }

  /// Ask AI about one story. The server answers from that story's stored coverage.
  Future<AskReply> askStory(String id, String question, List<Map<String, String>> history) async =>
      AskReply.fromJson(await _post('/stories/${Uri.encodeComponent(id)}/ask', {'question': question, 'history': history}));

  /// Ask AI about recent news. The server searches the last 7 days of stories.
  Future<AskReply> askNews(String question, List<Map<String, String>> history) async =>
      AskReply.fromJson(await _post('/ask', {'question': question, 'history': history}));

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final http.Response resp;
    try {
      resp = await _http
          .post(Uri.parse('$baseUrl$path'),
              headers: {'Accept': 'application/json', 'Content-Type': 'application/json'}, body: jsonEncode(body))
          .timeout(AppConfig.requestTimeout);
    } on TimeoutException {
      throw const ApiException('The AI assistant took too long to answer. Please try again.');
    } on http.ClientException {
      throw const ApiException('Could not reach the NewsVista server. Check your internet connection and try again.');
    }
    Map<String, dynamic>? json;
    try {
      json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    } on FormatException {
      json = null;
    }
    if (resp.statusCode != 200) {
      final detail = json?['detail'];
      throw ApiException(
        detail is String ? detail : 'The AI assistant is unavailable right now (${resp.statusCode}). Please try again.',
        statusCode: resp.statusCode,
        notFound: resp.statusCode == 404,
      );
    }
    if (json == null) throw const ApiException('The server sent an unexpected response.');
    return json;
  }

  /// Collection-run log (read-only), shown on the About screen.
  Future<Map<String, dynamic>> fetchStatus() => _get('/status', {'runs': '12'});

  Future<Map<String, dynamic>> _get(String path, [Map<String, String>? query]) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    final http.Response resp;
    try {
      resp = await _http.get(uri, headers: {'Accept': 'application/json'}).timeout(AppConfig.requestTimeout);
    } on TimeoutException {
      throw const ApiException('The NewsVista server took too long to respond. Please try again.', offline: true);
    } on http.ClientException {
      // Covers no connection, DNS failure and TLS errors on Android and web.
      throw const ApiException('Could not reach the NewsVista server. Check your internet connection and try again.',
          offline: true);
    }
    if (resp.statusCode == 404) {
      throw const ApiException(
        'This story is no longer available. It may have expired from the 7-day news window.',
        statusCode: 404,
        notFound: true,
      );
    }
    if (resp.statusCode == 503) {
      throw const ApiException('The news server is temporarily unavailable. Please try again shortly.',
          statusCode: 503, offline: true);
    }
    if (resp.statusCode != 200) {
      throw ApiException('The server returned an error (${resp.statusCode}). Please try again.',
          statusCode: resp.statusCode, offline: resp.statusCode >= 500);
    }
    try {
      return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    } on FormatException {
      throw const ApiException('The server sent an unexpected response.');
    }
  }
}
