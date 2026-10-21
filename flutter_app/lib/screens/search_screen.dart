import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/story_tiles.dart';
import 'home_screen.dart';

/// Search stored stories (server-side match on titles and feed excerpts).
class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.api});

  final ApiClient api;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  List<StorySummary>? _results;
  ApiException? _error;
  bool _loading = false;
  String _lastQuery = '';

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    final q = _controller.text.trim();
    if (q.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _loading = true;
      _error = null;
      _lastQuery = q;
    });
    try {
      final res = await widget.api.fetchStories(query: q, limit: 50);
      if (mounted) setState(() => _results = res.items);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Search', style: TextStyle(fontWeight: FontWeight.w800))),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
              child: TextField(
                controller: _controller,
                textInputAction: TextInputAction.search,
                onSubmitted: (_) => _search(),
                decoration: InputDecoration(
                  hintText: 'Search people, places, events…',
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: IconButton(icon: const Icon(Icons.arrow_forward), tooltip: 'Search', onPressed: _search),
                ),
              ),
            ),
            Expanded(child: _body()),
          ],
        ),
      ),
    );
  }

  Widget _body() {
    if (_loading) return const LoadingView(message: 'Searching…');
    if (_error != null) {
      return StatusView(icon: Icons.cloud_off, title: 'Search failed', message: _error!.message, actionLabel: 'Try again', onAction: _search);
    }
    final results = _results;
    if (results == null) {
      return const StatusView(
        icon: Icons.manage_search,
        title: 'Search the last 7 days',
        message: 'Find stories by a name, place or topic in their headlines and publisher excerpts.',
      );
    }
    if (results.isEmpty) {
      return StatusView(icon: Icons.search_off, title: 'No matches', message: 'No stories from the last 7 days match "$_lastQuery".');
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      itemCount: results.length + 1,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, i) {
        if (i == 0) {
          return Text('${results.length} ${results.length == 1 ? 'story' : 'stories'} for "$_lastQuery"',
              style: const TextStyle(color: AppColors.textMuted));
        }
        final s = results[i - 1];
        return StoryRow(story: s, onTap: () => openStory(context, widget.api, s));
      },
    );
  }
}
