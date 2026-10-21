import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme.dart';
import '../util/format.dart';
import '../util/open_link.dart';
import '../widgets/common.dart';
import 'perspective_screen.dart';

/// Screen 5 (AI Analysis tab). Shows the analysis already stored on the
/// server; opening it never calls the AI model.
class AnalysisView extends StatelessWidget {
  const AnalysisView({super.key, required this.story});

  final StoryDetail story;

  @override
  Widget build(BuildContext context) {
    final a = story.analysis;
    final c = a.content;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: AppColors.aiSoft, borderRadius: BorderRadius.circular(10)),
              child: const Icon(Icons.auto_awesome, color: AppColors.aiLight),
            ),
            const SizedBox(width: 10),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('AI Overview', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                  Text('A balanced explanation based on multiple sources.',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 12.5)),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (c == null) _unavailable(a) else ..._content(context, a, c),
      ],
    );
  }

  Widget _unavailable(Analysis a) {
    final (icon, title) = switch (a.status) {
      'failed' => (Icons.error_outline, 'AI analysis unavailable'),
      'expired_inputs' => (Icons.history_toggle_off, 'AI analysis being updated'),
      _ => (Icons.hourglass_empty, 'AI analysis not ready yet'),
    };
    return _Box(
      color: AppColors.aiLight,
      background: AppColors.aiSoft,
      icon: icon,
      title: title,
      children: [
        Text(a.statusMessage, style: const TextStyle(color: AppColors.textSubtle, height: 1.4)),
        const SizedBox(height: 8),
        const Text('The original coverage in the Sources tab is still available.',
            style: TextStyle(color: AppColors.textMuted, fontSize: 12.5)),
      ],
    );
  }

  List<Widget> _content(BuildContext context, Analysis a, AnalysisContent c) {
    return [
      Wrap(
        spacing: 8,
        runSpacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          AiLabel(generatedAt: a.generatedAt),
          Text('${a.model ?? 'model unknown'} · v${a.version}', style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
        ],
      ),
      if (a.status == 'outdated') ...[
        const SizedBox(height: 10),
        InfoBanner(a.statusMessage, icon: Icons.update, color: AppColors.disagree, background: AppColors.disagreeSoft),
      ],
      const SizedBox(height: 12),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(c.overview.text, style: const TextStyle(fontSize: 15.5, height: 1.5, color: AppColors.textSubtle)),
              const SizedBox(height: 10),
              CitationChips(numbers: c.overview.citations, content: c),
              if (c.overview.flag != null) ...[
                const SizedBox(height: 8),
                Text('Automated check: ${c.overview.flag}', style: const TextStyle(color: AppColors.disagree, fontSize: 12.5)),
              ],
            ],
          ),
        ),
      ),
      const SizedBox(height: 20),
      const _Heading(Icons.balance, 'Perspectives', 'How the retained coverage compares.'),
      _section('Agreement', Icons.check_circle, AppColors.agree, AppColors.agreeSoft, c.agreements, c,
          empty: story.publisherCount < 2 ? 'Only one publisher covered this story.' : 'No shared points identified.',
          note: 'Agreement among sources is not proof that a claim is true.'),
      _section('Disagreement', Icons.remove_circle, AppColors.disagree, AppColors.disagreeSoft, c.disagreements, c,
          empty: 'No meaningful disagreement found in the coverage.'),
      _section('Uncertainty', Icons.help, AppColors.uncertain, AppColors.uncertainSoft, c.uncertainties, c,
          empty: 'No open questions were flagged in the coverage.'),
      const SizedBox(height: 12),
      const _Heading(Icons.groups_outlined, 'Viewpoints', 'Positions held by people or groups in the coverage.'),
      if (c.perspectives.isEmpty)
        InfoBanner(c.perspectivesMessage ?? 'Insufficient evidence for distinct perspectives.',
            icon: Icons.balance, color: AppColors.textSubtle, background: AppColors.cardRaised)
      else
        for (var i = 0; i < c.perspectives.length; i++)
          ActionTile(
            title: c.perspectives[i].name,
            subtitle: c.perspectives[i].summary,
            leading: CircleAvatar(
              radius: 16,
              backgroundColor: AppColors.aiSoft,
              child: Text('${i + 1}', style: const TextStyle(color: AppColors.aiLight, fontWeight: FontWeight.w800)),
            ),
            trailingLabel: 'View',
            trailingIcon: Icons.chevron_right,
            color: AppColors.aiLight,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => PerspectiveScreen(story: story, content: c, index: i)),
            ),
          ),
      const SizedBox(height: 12),
      const _Heading(Icons.format_list_numbered, 'Supporting articles', 'Every [number] above links to one of these.'),
      for (final cit in c.citations)
        ActionTile(
          title: '[${cit.number}] ${cit.publisher}',
          subtitle: '${cit.title} · ${relativeTime(cit.publishedAt)}',
          leading: PublisherBadge(cit.publisher),
          onTap: () => openExternal(context, cit.url),
        ),
      const SizedBox(height: 8),
      InfoBanner(c.scopeDisclosure, icon: Icons.rule, color: AppColors.blueLight, background: AppColors.uncertainSoft),
      if (c.limitations.isNotEmpty) ...[
        const SizedBox(height: 16),
        const Text('Limitations noted by the AI', style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        for (final l in c.limitations)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text('• $l', style: const TextStyle(color: AppColors.textMuted, height: 1.4)),
          ),
      ],
      if (c.reviewNotes.isNotEmpty) ...[
        const SizedBox(height: 16),
        const Text('Automated fact checks', style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Text('The server removed or flagged ${c.reviewNotes.length} item(s) not supported by the cited articles:',
            style: const TextStyle(color: AppColors.textMuted, fontSize: 13)),
        const SizedBox(height: 4),
        for (final n in c.reviewNotes.take(6))
          Text('• $n', style: const TextStyle(color: AppColors.textMuted, fontSize: 12.5, height: 1.4)),
      ],
    ];
  }

  Widget _section(String title, IconData icon, Color color, Color background, List<CitedText> items, AnalysisContent c,
      {required String empty, String? note}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: _Box(
        color: color,
        background: background,
        icon: icon,
        title: title,
        children: [
          if (items.isEmpty)
            Text(empty, style: const TextStyle(color: AppColors.textMuted, height: 1.4))
          else
            for (final it in items) ...[
              Text(it.text, style: const TextStyle(color: AppColors.textSubtle, height: 1.4)),
              const SizedBox(height: 6),
              CitationChips(numbers: it.citations, content: c),
              const SizedBox(height: 10),
            ],
          if (note != null && items.isNotEmpty)
            Text(note, style: TextStyle(color: color, fontSize: 12, fontStyle: FontStyle.italic)),
        ],
      ),
    );
  }
}

class _Box extends StatelessWidget {
  const _Box({required this.color, required this.background, required this.icon, required this.title, required this.children});

  final Color color;
  final Color background;
  final IconData icon;
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 26),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: TextStyle(color: color, fontWeight: FontWeight.w800, fontSize: 15.5)),
                const SizedBox(height: 6),
                ...children,
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.icon, this.title, this.subtitle);

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Icon(icon, color: AppColors.aiLight, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: 16.5, fontWeight: FontWeight.w800)),
                Text(subtitle, style: const TextStyle(color: AppColors.textMuted, fontSize: 12.5)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
