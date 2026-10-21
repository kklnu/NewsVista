import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../config.dart';
import '../theme.dart';
import '../util/format.dart';
import '../widgets/common.dart';
import '../widgets/story_tiles.dart';
import 'story_screen.dart';

/// Feed filters shown as chips. Categories come from the feed sections the
/// articles were published in; "Multi-source" = covered by 2+ publishers.
class FeedFilter {
  const FeedFilter(this.label, {this.category, this.minPublishers = 1});

  final String label;
  final String? category;
  final int minPublishers;
}

const feedFilters = [
  FeedFilter('Top Stories'),
  FeedFilter('Multi-source', minPublishers: 2),
  FeedFilter('World', category: 'world'),
  FeedFilter('Politics', category: 'politics'),
  FeedFilter('U.S.', category: 'us'),
];

void openStory(BuildContext context, ApiClient api, StorySummary s) {
  Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => StoryScreen(api: api, storyId: s.id, initialHeadline: s.headline, initialImageUrl: s.imageUrl),
    ),
  );
}

/// Screen 1: Top stories. One card per event, newest first.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.api, this.onSearch});

  final ApiClient api;
  final VoidCallback? onSearch;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final List<StorySummary> _stories = [];
  StoryListResponse? _last;
  ApiException? _error;
  bool _loading = true;
  bool _loadingMore = false;
  FeedFilter _filter = feedFilters.first;
  DateTime? _syncedAt;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<StoryListResponse> _fetch({int offset = 0}) => widget.api.fetchStories(
        offset: offset,
        minPublishers: _filter.minPublishers,
        category: _filter.category,
      );

  Future<void> _load() async {
    setState(() {
      _loading = _stories.isEmpty;
      _error = null;
    });
    try {
      final res = await _fetch();
      if (!mounted) return;
      setState(() {
        _last = res;
        _stories
          ..clear()
          ..addAll(res.items);
        _syncedAt = DateTime.now();
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
      if (_stories.isNotEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Refresh failed: ${e.message} Showing the stories loaded earlier.')),
        );
      }
    }
  }

  Future<void> _loadMore() async {
    setState(() => _loadingMore = true);
    try {
      final res = await _fetch(offset: _stories.length);
      if (!mounted) return;
      setState(() {
        final known = _stories.map((s) => s.id).toSet();
        _stories.addAll(res.items.where((s) => !known.contains(s.id)));
        _last = res;
      });
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  void _setFilter(FeedFilter f) {
    if (f == _filter) return;
    setState(() {
      _filter = f;
      _stories.clear();
    });
    _load();
  }

  /// Ordering (documented in README): the TOP STORY is the newest story covered
  /// by 2+ publishers (falls back to the newest story); every other story
  /// follows newest first.
  List<StorySummary> get _ordered {
    if (_stories.isEmpty) return _stories;
    final top = _stories.firstWhere((s) => s.publisherCount >= 2, orElse: () => _stories.first);
    return [top, ..._stories.where((s) => s.id != top.id)];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 64,
        titleSpacing: 16,
        title: const Row(
          children: [
            AppLogo(size: 34),
            SizedBox(width: 10),
            Text(AppConfig.appName, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 22)),
          ],
        ),
        actions: [
          IconButton(tooltip: 'Search stories', icon: const Icon(Icons.search), onPressed: widget.onSearch),
          IconButton(
            tooltip: 'Refresh stories',
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            _chips(),
            Expanded(child: _body()),
          ],
        ),
      ),
    );
  }

  Widget _chips() {
    return SizedBox(
      height: 52,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.fromLTRB(16, 6, 16, 8),
        itemCount: feedFilters.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final f = feedFilters[i];
          final selected = f == _filter;
          return ChoiceChip(
            label: Text(f.label),
            selected: selected,
            showCheckmark: false,
            onSelected: (_) => _setFilter(f),
            labelStyle: TextStyle(
              color: selected ? Colors.white : AppColors.textSubtle,
              fontWeight: FontWeight.w600,
            ),
            selectedColor: AppColors.blue,
            backgroundColor: AppColors.card,
            side: BorderSide(color: selected ? AppColors.blue : AppColors.border),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          );
        },
      ),
    );
  }

  Widget _body() {
    if (_loading && _stories.isEmpty) return const StoryListSkeleton();
    if (_error != null && _stories.isEmpty) {
      return StatusView(
        icon: Icons.cloud_off,
        title: 'Could not load stories',
        message: _error!.message,
        actionLabel: 'Try again',
        onAction: _load,
      );
    }
    final total = _last?.total ?? 0;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        itemCount: _stories.length + 2,
        separatorBuilder: (_, _) => const SizedBox(height: 12),
        itemBuilder: (context, i) {
          if (i == 0) return _status();
          if (i == _stories.length + 1) return _footer(total);
          final story = _ordered[i - 1];
          void open() => openStory(context, widget.api, story);
          if (i == 1) return HeroStoryCard(story: story, onTap: open);
          final row = StoryRow(story: story, onTap: open);
          if (i != 2) return row;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.only(top: 6, bottom: 12),
                child: Text('More stories', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
              ),
              row,
            ],
          );
        },
      ),
    );
  }

  Widget _status() {
    final collected = _last?.lastSuccessfulCollectionAt;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.schedule, size: 15, color: AppColors.textMuted),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                collected == null
                    ? 'Server has not completed a collection yet'
                    : 'Updated ${relativeTime(collected)} · ${_last?.total ?? 0} stories · newest first',
                style: const TextStyle(color: AppColors.textMuted, fontSize: 12.5),
              ),
            ),
          ],
        ),
        if (_last?.cachedAt != null) ...[
          const SizedBox(height: 8),
          OfflineBanner(savedAt: _last!.cachedAt!, onRetry: _load),
        ] else if (_error != null) ...[
          const SizedBox(height: 8),
          InfoBanner('Offline or server unreachable. Showing stories loaded ${relativeTime(_syncedAt)}. Pull down to retry.',
              icon: Icons.wifi_off, color: AppColors.error, background: AppColors.errorSoft),
        ],
      ],
    );
  }

  Widget _footer(int total) {
    if (_stories.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 48),
        child: StatusView(
          icon: Icons.inbox_outlined,
          title: 'No stories yet',
          message: 'The server has no stories from the last 7 days for this view. '
              'New stories are collected every hour.',
        ),
      );
    }
    if (_stories.length < total) {
      return Center(
        child: _loadingMore
            ? const Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())
            : OutlinedButton(onPressed: _loadMore, child: Text('Load more (${total - _stories.length} left)')),
      );
    }
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 8),
      child: Text('Newest first · Only the most recent 7 days',
          textAlign: TextAlign.center, style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
    );
  }
}

class AppLogo extends StatelessWidget {
  const AppLogo({super.key, this.size = 32});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(size * 0.28),
        gradient: const LinearGradient(colors: [AppColors.blue, AppColors.ai]),
      ),
      child: Icon(Icons.public, color: Colors.white, size: size * 0.66),
    );
  }
}
