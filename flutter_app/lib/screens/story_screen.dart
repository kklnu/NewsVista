import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../theme.dart';
import '../util/format.dart';
import '../util/open_link.dart';
import '../widgets/common.dart';
import 'analysis_view.dart';
import 'assistant_screen.dart';

/// Screen 2: Story detail. Tabs: Overview · Sources · Background · AI Analysis.
class StoryScreen extends StatefulWidget {
  const StoryScreen({
    super.key,
    required this.api,
    required this.storyId,
    required this.initialHeadline,
    this.initialImageUrl,
  });

  final ApiClient api;
  final String storyId;
  final String initialHeadline;

  /// Image from the list card, so it can animate into the header while loading.
  final String? initialImageUrl;

  @override
  State<StoryScreen> createState() => _StoryScreenState();
}

class _StoryScreenState extends State<StoryScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 4, vsync: this)
    ..addListener(() {
      if (mounted) setState(() {});
    });
  final _scroll = ScrollController();
  bool _collapsed = false; // header image scrolled away -> show headline in the top bar
  StoryDetail? _story;
  ApiException? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final collapsed = _scroll.hasClients && _scroll.offset > 170;
      if (collapsed != _collapsed) setState(() => _collapsed = collapsed);
    });
    _load();
  }

  @override
  void dispose() {
    _scroll.dispose();
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final story = await widget.api.fetchStory(widget.storyId);
      if (mounted) setState(() => _story = story);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = _story;
    if (s == null && _loading) return _loadingLayout();
    if (s == null) {
      return Scaffold(
        appBar: AppBar(leading: BackButton(onPressed: () => Navigator.of(context).maybePop())),
        body: SafeArea(child: _placeholder()),
      );
    }
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => showStoryAssistant(context, widget.api, s),
        backgroundColor: AppColors.ai,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.auto_awesome),
        label: const Text('Ask AI', style: TextStyle(fontWeight: FontWeight.w700)),
        tooltip: 'Ask AI about this story',
      ),
      body: CustomScrollView(
        controller: _scroll,
        slivers: [
          SliverAppBar(
            pinned: true,
            expandedHeight: 220,
            backgroundColor: AppColors.background,
            title: AnimatedOpacity(
              opacity: _collapsed ? 1 : 0,
              duration: const Duration(milliseconds: 200),
              child: Text(s.headline,
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
            leading: _CircleButton(icon: Icons.arrow_back, tooltip: 'Back to stories', onTap: () => Navigator.of(context).maybePop()),
            actions: [
              _CircleButton(icon: Icons.refresh, tooltip: 'Reload story', onTap: _loading ? null : _load),
              const SizedBox(width: 8),
            ],
            flexibleSpace: FlexibleSpaceBar(
              background: Stack(
                fit: StackFit.expand,
                children: [
                  Hero(tag: 'story-image-${s.id}', child: NetImage(s.imageUrl ?? widget.initialImageUrl)),
                  const DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [Color(0x660B1222), Colors.transparent, AppColors.background],
                        stops: [0, 0.4, 1],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(child: _header(s)),
          SliverPersistentHeader(pinned: true, delegate: _TabsHeader(_tabBar())),
          // One scroll view for header + tab content, so content never slides
          // under the pinned tab bar.
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
            sliver: SliverList.list(
              children: switch (_tabs.index) {
                0 => _overview(s),
                1 => _sources(s),
                2 => _background(s),
                _ => [AnalysisView(story: s)],
              },
            ),
          ),
        ],
      ),
    );
  }

  /// Skeleton shaped like the story page; the list image animates into place.
  Widget _loadingLayout() {
    return Scaffold(
      body: ListView(
        padding: EdgeInsets.zero,
        physics: const NeverScrollableScrollPhysics(),
        children: [
          SizedBox(
            height: 220 + MediaQuery.paddingOf(context).top,
            child: Stack(
              fit: StackFit.expand,
              children: [
                Hero(tag: 'story-image-${widget.storyId}', child: NetImage(widget.initialImageUrl)),
                Positioned(
                  left: 0,
                  top: MediaQuery.paddingOf(context).top,
                  child: _CircleButton(icon: Icons.arrow_back, tooltip: 'Back to stories',
                      onTap: () => Navigator.of(context).maybePop()),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(widget.initialHeadline,
                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800, height: 1.22)),
                const SizedBox(height: 16),
                const Skeleton(width: 200, height: 14),
                const SizedBox(height: 20),
                const Skeleton(height: 48, radius: 14),
                const SizedBox(height: 16),
                const Skeleton(height: 160, radius: 16),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _placeholder() {
    if (_loading) return const LoadingView(message: 'Loading story…');
    final e = _error!;
    return StatusView(
      icon: e.notFound ? Icons.history_toggle_off : Icons.cloud_off,
      title: e.notFound ? 'Story unavailable' : 'Could not load this story',
      message: e.message,
      actionLabel: e.notFound ? null : 'Try again',
      onAction: _load,
      secondaryLabel: 'Back to stories',
      onSecondary: () => Navigator.of(context).maybePop(),
    );
  }

  Widget _header(StoryDetail s) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (s.cachedAt != null) ...[
            OfflineBanner(savedAt: s.cachedAt!, onRetry: _load),
            const SizedBox(height: 12),
          ],
          Text(s.headline, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800, height: 1.22)),
          const SizedBox(height: 10),
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 6,
            runSpacing: 6,
            children: [
              Text('Covered by ${s.publisherCount} ${s.publisherCount == 1 ? 'publisher' : 'publishers'}',
                  style: const TextStyle(color: AppColors.textMuted)),
              const SizedBox(width: 4),
              for (final p in s.publishers) PublisherBadge(p.publisher, size: 22),
            ],
          ),
          const SizedBox(height: 4),
          Text('Latest article ${relativeTime(s.latestPublishedAt)}',
              style: const TextStyle(color: AppColors.textMuted, fontSize: 12.5)),
        ],
      ),
    );
  }

  TabBar _tabBar() {
    return TabBar(
      controller: _tabs,
      isScrollable: true,
      tabAlignment: TabAlignment.start,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      labelPadding: const EdgeInsets.symmetric(horizontal: 14),
      indicator: BoxDecoration(color: AppColors.blue, borderRadius: BorderRadius.circular(10)),
      indicatorPadding: const EdgeInsets.symmetric(vertical: 6),
      tabs: const [
        Tab(text: 'Overview'),
        Tab(text: 'Sources'),
        Tab(text: 'Background'),
        Tab(text: 'AI Analysis'),
      ],
    );
  }

  // ---------------------------------------------------------------- Overview
  List<Widget> _overview(StoryDetail s) {
    final o = s.overview;
    final content = s.analysis.content;
    return [
      _Panel(
        icon: Icons.description_outlined,
        title: 'Quick Summary',
        trailing: o.isAi ? const AiLabel() : const Pill('Publisher excerpt', icon: Icons.format_quote, color: AppColors.textSubtle, background: AppColors.cardRaised),
        children: [
          Text(o.text, style: const TextStyle(fontSize: 15.5, height: 1.5, color: AppColors.textSubtle)),
          const SizedBox(height: 10),
          Text(
            o.isAi
                ? 'Written by AI from the coverage in Sources · ${fullTime(o.generatedAt)}. Citations are in AI Analysis.'
                : '${o.label}. The AI summary for this story has not been generated yet.',
            style: const TextStyle(color: AppColors.textMuted, fontSize: 12.5),
          ),
        ],
      ),
      const SizedBox(height: 12),
      _Panel(
        icon: Icons.checklist,
        title: 'Key Details',
        trailing: content != null && content.keyPoints.isNotEmpty ? const AiLabel() : null,
        children: content != null && content.keyPoints.isNotEmpty
            ? [
                for (final k in content.keyPoints)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Padding(
                          padding: EdgeInsets.only(top: 2),
                          child: Icon(Icons.check_circle, size: 18, color: AppColors.blueLight),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(k.text, style: const TextStyle(height: 1.4)),
                              const SizedBox(height: 6),
                              CitationChips(numbers: k.citations, content: content),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
              ]
            : [
                const Text('What each publisher reports (headlines, original wording):',
                    style: TextStyle(color: AppColors.textMuted, fontSize: 12.5)),
                const SizedBox(height: 10),
                for (final p in s.publishers)
                  for (final a in p.articles.take(2))
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          PublisherBadge(p.publisher, size: 20),
                          const SizedBox(width: 10),
                          Expanded(child: Text(a.title, style: const TextStyle(height: 1.35))),
                        ],
                      ),
                    ),
              ],
      ),
      const SizedBox(height: 16),
      FilledButton.icon(
        onPressed: () => _tabs.animateTo(3),
        style: FilledButton.styleFrom(backgroundColor: AppColors.ai),
        icon: const Icon(Icons.auto_awesome),
        label: const Text('View AI analysis'),
      ),
      const SizedBox(height: 8),
      OutlinedButton.icon(
        onPressed: () => _tabs.animateTo(1),
        icon: const Icon(Icons.newspaper),
        label: const Text('Read original coverage'),
      ),
    ];
  }

  // ----------------------------------------------------------------- Sources
  List<Widget> _sources(StoryDetail s) {
    return [
      const _TabHeading(Icons.newspaper, 'Original Coverage', 'Read how different publishers are covering this event.'),
      for (final p in s.publishers) _publisherCard(p),
      const SizedBox(height: 4),
      const Text('Only publishers that covered this story are listed. Pages open in your browser.',
          style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
      const SizedBox(height: 16),
      Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.aiSoft,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.ai.withValues(alpha: 0.4)),
        ),
        child: const Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.lightbulb_outline, color: AppColors.aiLight),
            SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Why different coverage?', style: TextStyle(fontWeight: FontWeight.w800, color: AppColors.aiLight)),
                  SizedBox(height: 6),
                  Text(
                    'Each news organization has its own focus, audience and editorial choices. Reading several '
                    'sources helps you get a more complete understanding of the event.',
                    style: TextStyle(color: AppColors.textSubtle, height: 1.4),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ];
  }

  Widget _publisherCard(PublisherCoverage p) {
    final single = p.articles.length == 1;
    final first = p.articles.first;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => single ? openExternal(context, first.url) : _chooseArticle(p),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                PublisherBadge(p.publisher, size: 34),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(p.publisher, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15.5)),
                      const SizedBox(height: 3),
                      Text(single ? first.title : '${p.articles.length} articles on this story — tap to choose',
                          maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.textSubtle, height: 1.3)),
                      const SizedBox(height: 4),
                      Text(relativeTime(first.publishedAt), style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Icon(single ? Icons.open_in_new : Icons.list, color: AppColors.blueLight, semanticLabel: single ? 'Open' : 'Choose'),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _chooseArticle(PublisherCoverage p) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      backgroundColor: AppColors.navy,
      builder: (sheetContext) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.of(sheetContext).size.height * 0.75),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            children: [
              Text('${p.publisher} coverage', style: Theme.of(sheetContext).textTheme.titleLarge),
              const SizedBox(height: 12),
              for (final a in p.articles)
                ActionTile(
                  title: a.title,
                  subtitle: '${fullTime(a.publishedAt)}${a.excerpt.isNotEmpty ? ' · ${a.excerpt}' : ''}',
                  onTap: () {
                    Navigator.of(sheetContext).pop();
                    openExternal(context, a.url);
                  },
                ),
            ],
          ),
        ),
      ),
    );
  }

  // -------------------------------------------------------------- Background
  List<Widget> _background(StoryDetail s) {
    return [
      const _TabHeading(Icons.menu_book_outlined, 'Background Information',
          'Learn more about the people, places, and key topics related to this event.'),
      for (final b in s.background.links)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Card(
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: () => openExternal(context, b.url),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: NetImage(b.thumbnailUrl, width: 72, height: 72, icon: Icons.menu_book),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(b.title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15.5)),
                          if (b.description.isNotEmpty) ...[
                            const SizedBox(height: 3),
                            Text(b.description, maxLines: 2, overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: AppColors.textSubtle, height: 1.3)),
                          ],
                          const SizedBox(height: 4),
                          Text(b.provider, style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
                        ],
                      ),
                    ),
                    const Icon(Icons.open_in_new, color: AppColors.blueLight, semanticLabel: 'Open'),
                  ],
                ),
              ),
            ),
          ),
        ),
      if (s.background.links.isEmpty)
        _Panel(
          icon: Icons.info_outline,
          title: 'No background resource available',
          children: [
            Text(
              s.background.status == 'pending'
                  ? 'The server has not searched for background on this story yet. It checks new stories every hour.'
                  : 'The server only links a reference page when it clearly matches people, places or topics in this '
                      'story, so nothing unrelated is shown here.',
              style: const TextStyle(color: AppColors.textSubtle, height: 1.4),
            ),
          ],
        ),
    ];
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.icon, required this.title, required this.children, this.trailing});

  final IconData icon;
  final String title;
  final List<Widget> children;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(7),
                  decoration: BoxDecoration(color: AppColors.blueSoft, borderRadius: BorderRadius.circular(9)),
                  child: Icon(icon, size: 18, color: AppColors.blueLight),
                ),
                const SizedBox(width: 10),
                Expanded(child: Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16.5))),
                if (trailing != null) Flexible(child: trailing!),
              ],
            ),
            const SizedBox(height: 12),
            ...children,
          ],
        ),
      ),
    );
  }
}

class _TabHeading extends StatelessWidget {
  const _TabHeading(this.icon, this.title, this.subtitle);

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, color: AppColors.blueLight, size: 22),
            const SizedBox(width: 8),
            Expanded(child: Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800))),
          ]),
          const SizedBox(height: 4),
          Text(subtitle, style: const TextStyle(color: AppColors.textMuted)),
        ],
      ),
    );
  }
}

class _CircleButton extends StatelessWidget {
  const _CircleButton({required this.icon, required this.tooltip, required this.onTap});

  final IconData icon;
  final String tooltip;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(6),
      child: Material(
        color: const Color(0x990B1222),
        shape: const CircleBorder(),
        child: IconButton(icon: Icon(icon, color: Colors.white), tooltip: tooltip, onPressed: onTap),
      ),
    );
  }
}

class _TabsHeader extends SliverPersistentHeaderDelegate {
  _TabsHeader(this.tabBar);

  final TabBar tabBar;

  @override
  double get minExtent => 56;

  @override
  double get maxExtent => 56;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    return Container(
      color: AppColors.background,
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(14)),
        child: tabBar,
      ),
    );
  }

  @override
  bool shouldRebuild(_TabsHeader oldDelegate) => oldDelegate.tabBar != tabBar;
}
