import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme.dart';
import '../util/format.dart';
import 'common.dart';

/// Large card for the newest story (mockup: "Top Stories" hero).
class HeroStoryCard extends StatelessWidget {
  const HeroStoryCard({super.key, required this.story, required this.onTap});

  final StorySummary story;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 16 / 9,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Hero(tag: 'story-image-${story.id}', child: NetImage(story.imageUrl)),
                  const DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [Colors.transparent, Color(0xCC0B1222)],
                        stops: [0.45, 1],
                      ),
                    ),
                  ),
                  Positioned(
                    left: 12,
                    top: 12,
                    child: _Tag('TOP STORY', AppColors.badge),
                  ),
                  Positioned(
                    right: 12,
                    top: 12,
                    child: _Tag(relativeTime(story.latestPublishedAt), const Color(0xB30F172A)),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    story.headline,
                    style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w800, height: 1.25),
                  ),
                  if (story.summary.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      story.summary,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: AppColors.textSubtle, height: 1.4),
                    ),
                    const SizedBox(height: 4),
                    Text(story.summaryLabel,
                        style: const TextStyle(color: AppColors.textMuted, fontSize: 11.5)),
                  ],
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      for (final p in story.publishers.take(5)) ...[PublisherBadge(p, size: 24), const SizedBox(width: 6)],
                      const Spacer(),
                      SourcesCount(story.publisherCount, highlight: true),
                      const SizedBox(width: 4),
                      const Icon(Icons.arrow_forward, size: 18, color: AppColors.blueLight),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Compact row with thumbnail (mockup: list under the hero card).
class StoryRow extends StatelessWidget {
  const StoryRow({super.key, required this.story, required this.onTap});

  final StorySummary story;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: Hero(tag: 'story-image-${story.id}', child: NetImage(story.imageUrl, width: 104, height: 80)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(relativeTime(story.latestPublishedAt),
                        style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
                    const SizedBox(height: 3),
                    Text(
                      story.headline,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15, height: 1.3),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        SourcesCount(story.publisherCount, highlight: story.publisherCount > 1),
                        const Spacer(),
                        if (story.hasAi) const Icon(Icons.auto_awesome, size: 16, color: AppColors.aiLight),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class SourcesCount extends StatelessWidget {
  const SourcesCount(this.count, {super.key, this.highlight = false});

  final int count;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    final color = highlight ? AppColors.blueLight : AppColors.textMuted;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.layers_outlined, size: 15, color: color),
        const SizedBox(width: 4),
        Text('$count ${count == 1 ? 'source' : 'sources'}',
            style: TextStyle(color: color, fontSize: 12.5, fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.text, this.color);

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
      child: Text(text, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 0.4)),
    );
  }
}
