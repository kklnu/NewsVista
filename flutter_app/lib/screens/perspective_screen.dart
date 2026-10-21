import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme.dart';
import '../util/format.dart';
import '../util/open_link.dart';
import '../widgets/common.dart';

/// Screen 6: One viewpoint with its supported claims and numbered citations.
class PerspectiveScreen extends StatelessWidget {
  const PerspectiveScreen({super.key, required this.story, required this.content, required this.index});

  final StoryDetail story;
  final AnalysisContent content;
  final int index;

  @override
  Widget build(BuildContext context) {
    final p = content.perspectives[index];
    final cited = p.citationNumbers;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Perspective'),
        leading: BackButton(onPressed: () => Navigator.of(context).maybePop()),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            Align(alignment: Alignment.centerLeft, child: AiLabel(generatedAt: story.analysis.generatedAt)),
            const SizedBox(height: 10),
            Text(p.name, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 4),
            Text('Viewpoint ${index + 1} of ${content.perspectives.length} · ${story.headline}',
                style: const TextStyle(color: AppColors.textSecondary, fontSize: 13)),
            if (p.summary.isNotEmpty) ...[
              const SizedBox(height: 14),
              Text(p.summary, style: const TextStyle(fontSize: 15.5, height: 1.45)),
            ],
            SectionTitle('Supported claims', icon: Icons.fact_check_outlined),
            for (final claim in p.claims)
              Card(
                margin: const EdgeInsets.only(bottom: 10),
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(claim.text, style: const TextStyle(height: 1.4)),
                      const SizedBox(height: 8),
                      CitationChips(numbers: claim.citations, content: content),
                    ],
                  ),
                ),
              ),
            SectionTitle('Evidence and limits', icon: Icons.balance),
            InfoBanner(
              [
                'This is an attributed viewpoint reported in the coverage, not NewsVista\'s opinion.',
                if (p.caveats.isNotEmpty) p.caveats,
              ].join(' '),
              color: AppColors.disagree,
              background: AppColors.disagreeLight,
              icon: Icons.info_outline,
            ),
            SectionTitle('Supporting coverage', icon: Icons.format_list_numbered),
            for (final n in cited)
              if (content.citation(n) case final c?)
                ActionTile(
                  title: '[${c.number}] ${c.publisher}',
                  subtitle: '${c.title} · ${relativeTime(c.publishedAt)}',
                  leading: PublisherBadge(c.publisher),
                  onTap: () => openExternal(context, c.url),
                ),
            if (content.perspectives.length > 1) ...[
              SectionTitle('Switch viewpoint', icon: Icons.swap_horiz),
              for (var i = 0; i < content.perspectives.length; i++)
                if (i != index)
                  ActionTile(
                    title: content.perspectives[i].name,
                    subtitle: content.perspectives[i].summary,
                    trailingLabel: 'Switch',
                    trailingIcon: Icons.swap_horiz,
                    color: AppColors.ai,
                    onTap: () => Navigator.of(context).pushReplacement(
                      MaterialPageRoute(builder: (_) => PerspectiveScreen(story: story, content: content, index: i)),
                    ),
                  ),
            ],
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => Navigator.of(context).maybePop(),
              icon: const Icon(Icons.arrow_back),
              label: const Text('Back to AI analysis'),
            ),
          ],
        ),
      ),
    );
  }
}
