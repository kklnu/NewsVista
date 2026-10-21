import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Offline copy of server results (optional feature in the assignment, §6).
///
/// - Only server-produced JSON is cached; the phone never collects news itself.
/// - Cached content still obeys the 168-hour window: expired stories/articles are
///   removed when read back, even while offline.
/// - A cached AI analysis that relied on an expired article is hidden, exactly
///   like the server does ("expired_inputs").
class NewsCache {
  NewsCache({this.window = const Duration(hours: 168), DateTime Function()? clock})
      : _now = clock ?? DateTime.now;

  final Duration window;
  final DateTime Function() _now;
  static const _maxStories = 40;

  Future<SharedPreferences?> _prefs() async {
    try {
      return await SharedPreferences.getInstance();
    } catch (_) {
      return null; // storage unavailable: the app simply works without a cache
    }
  }

  Future<void> save(String key, Map<String, dynamic> json) async {
    final prefs = await _prefs();
    if (prefs == null) return;
    await prefs.setString('nv:$key', jsonEncode({'saved_at': _now().toUtc().toIso8601String(), 'json': json}));
    if (key.startsWith('story:')) {
      final order = prefs.getStringList('nv:story-order') ?? [];
      order
        ..remove(key)
        ..add(key);
      while (order.length > _maxStories) {
        await prefs.remove('nv:${order.removeAt(0)}');
      }
      await prefs.setStringList('nv:story-order', order);
    }
  }

  /// Returns (json, savedAt) with expired content removed, or null.
  Future<(Map<String, dynamic>, DateTime)?> load(String key) async {
    final prefs = await _prefs();
    final raw = prefs?.getString('nv:$key');
    if (raw == null) return null;
    try {
      final wrapper = jsonDecode(raw) as Map<String, dynamic>;
      final savedAt = DateTime.parse(wrapper['saved_at'] as String).toLocal();
      final json = wrapper['json'] as Map<String, dynamic>;
      final cleaned = key.startsWith('story:') ? _cleanStory(json) : _cleanList(json);
      return cleaned == null ? null : (cleaned, savedAt);
    } catch (_) {
      return null;
    }
  }

  bool _expired(dynamic iso) {
    final t = iso is String ? DateTime.tryParse(iso) : null;
    return t == null || t.isBefore(_now().toUtc().subtract(window));
  }

  Map<String, dynamic> _cleanList(Map<String, dynamic> json) {
    final items = (json['items'] as List).cast<Map<String, dynamic>>();
    final kept = items.where((s) => !_expired(s['latest_published_at'])).toList();
    return {...json, 'items': kept, 'total': kept.length};
  }

  Map<String, dynamic>? _cleanStory(Map<String, dynamic> json) {
    var removed = 0;
    final publishers = <Map<String, dynamic>>[];
    for (final p in (json['publishers'] as List).cast<Map<String, dynamic>>()) {
      final articles = (p['articles'] as List).cast<Map<String, dynamic>>();
      final kept = articles.where((a) => !_expired(a['published_at'])).toList();
      removed += articles.length - kept.length;
      if (kept.isNotEmpty) publishers.add({...p, 'articles': kept, 'article_count': kept.length});
    }
    if (publishers.isEmpty) return null; // whole story expired: do not show it offline
    final out = {...json, 'publishers': publishers, 'publisher_count': publishers.length};
    if (removed > 0) {
      final analysis = Map<String, dynamic>.from(json['analysis'] as Map);
      analysis['content'] = null;
      analysis['status'] = 'expired_inputs';
      analysis['status_message'] =
          'Some articles this analysis relied on have expired, so it is hidden until you are back online.';
      out['analysis'] = analysis;
      final lead = (publishers.first['articles'] as List).first as Map<String, dynamic>;
      out['overview'] = {
        'kind': 'publisher_excerpt',
        'label': 'Publisher excerpt — ${publishers.first['publisher']} (original wording)',
        'text': (lead['excerpt'] as String?)?.isNotEmpty == true ? lead['excerpt'] : lead['title'],
        'generated_at': null,
      };
    }
    return out;
  }
}
