import 'dart:async';

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme.dart';
import '../util/format.dart';
import '../util/open_link.dart';

/// Centered status for empty / error states, always with a way forward.
class StatusView extends StatelessWidget {
  const StatusView({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    this.actionLabel,
    this.onAction,
    this.secondaryLabel,
    this.onSecondary,
  });

  final IconData icon;
  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final String? secondaryLabel;
  final VoidCallback? onSecondary;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 56, color: AppColors.textSecondary),
            const SizedBox(height: 16),
            Text(title, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center, style: const TextStyle(color: AppColors.textSecondary, height: 1.4)),
            if (actionLabel != null) ...[
              const SizedBox(height: 24),
              FilledButton.icon(onPressed: onAction, icon: const Icon(Icons.refresh), label: Text(actionLabel!)),
            ],
            if (secondaryLabel != null) ...[
              const SizedBox(height: 8),
              TextButton(onPressed: onSecondary, child: Text(secondaryLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

/// Spinner that explains a slow first load (free servers sleep when idle).
class LoadingView extends StatefulWidget {
  const LoadingView({super.key, this.message = 'Loading stories…'});

  final String message;

  @override
  State<LoadingView> createState() => _LoadingViewState();
}

class _LoadingViewState extends State<LoadingView> {
  bool _slow = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer(const Duration(seconds: 6), () {
      if (mounted) setState(() => _slow = true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 16),
            Text(widget.message, style: const TextStyle(color: AppColors.textSecondary)),
            if (_slow) ...[
              const SizedBox(height: 8),
              const Text(
                'Still working… the server may take up to a minute to wake up.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.icon, this.trailing});

  final String text;
  final IconData? icon;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 10),
      child: Row(
        children: [
          if (icon != null) ...[Icon(icon, size: 20, color: AppColors.teal), const SizedBox(width: 8)],
          Expanded(
            child: Text(text,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

class Pill extends StatelessWidget {
  const Pill(this.label, {super.key, this.color = AppColors.teal, this.background = AppColors.tealLight, this.icon});

  final String label;
  final Color color;
  final Color background;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 14, color: color), const SizedBox(width: 4)],
          Flexible(
            child: Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}

class AiLabel extends StatelessWidget {
  const AiLabel({super.key, this.generatedAt});

  final DateTime? generatedAt;

  @override
  Widget build(BuildContext context) {
    final when = generatedAt == null ? '' : ' · ${fullTime(generatedAt)}';
    return Pill('AI-generated$when', color: AppColors.ai, background: AppColors.aiLight, icon: Icons.auto_awesome);
  }
}

class PublisherBadge extends StatelessWidget {
  const PublisherBadge(this.publisher, {super.key, this.size = 32});

  final String publisher;
  final double size;

  static const _colors = {
    'BBC News': (Color(0xFFFFFFFF), Color(0xFF111111)),
    'NPR': (Color(0xFFD62021), Color(0xFFFFFFFF)),
    'Fox News': (Color(0xFF003366), Color(0xFFFFFFFF)),
    'The Guardian': (Color(0xFF052962), Color(0xFFFFFFFF)),
    'CBS News': (Color(0xFF1A1A1A), Color(0xFFFFFFFF)),
  };

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = _colors[publisher] ?? (AppColors.cardRaised, AppColors.text);
    return Semantics(
      label: publisher,
      child: Container(
        width: size * 1.35,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: Colors.white.withValues(alpha: 0.15)),
        ),
        child: Text(
          publisherAbbrev(publisher),
          style: TextStyle(color: fg, fontSize: size * 0.34, fontWeight: FontWeight.w900, letterSpacing: 0.4),
        ),
      ),
    );
  }
}

/// Image from a URL with a branded placeholder when missing or failing.
/// On the web, falls back to an <img> element for images without CORS headers.
class NetImage extends StatelessWidget {
  const NetImage(this.url, {super.key, this.width, this.height, this.icon = Icons.public});

  final String? url;
  final double? width;
  final double? height;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final placeholder = Container(
      width: width,
      height: height,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [Color(0xFF1E3A6E), Color(0xFF16213A), Color(0xFF2E2556)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Icon(icon, color: Colors.white.withValues(alpha: 0.25), size: 36),
    );
    if (url == null || url!.isEmpty) return placeholder;
    return Image.network(
      url!,
      width: width,
      height: height,
      fit: BoxFit.cover,
      webHtmlElementStrategy: WebHtmlElementStrategy.fallback,
      errorBuilder: (_, _, _) => placeholder,
      loadingBuilder: (_, child, progress) => progress == null ? child : placeholder,
    );
  }
}

/// A full-width, clearly labeled tap target (min 56dp tall).
class ActionTile extends StatelessWidget {
  const ActionTile({
    super.key,
    required this.title,
    this.subtitle,
    this.leading,
    this.trailingLabel = 'Open',
    this.trailingIcon = Icons.open_in_new,
    required this.onTap,
    this.color = AppColors.teal,
  });

  final String title;
  final String? subtitle;
  final Widget? leading;
  final String trailingLabel;
  final IconData trailingIcon;
  final VoidCallback onTap;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: AppColors.card,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: AppColors.border),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 56),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                children: [
                  if (leading != null) ...[leading!, const SizedBox(width: 12)],
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                        if (subtitle != null && subtitle!.isNotEmpty) ...[
                          const SizedBox(height: 2),
                          Text(subtitle!,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(color: AppColors.textSecondary, fontSize: 13)),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(trailingLabel, style: TextStyle(color: color, fontWeight: FontWeight.w700)),
                  const SizedBox(width: 4),
                  Icon(trailingIcon, size: 18, color: color),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Tappable [1] [2] citation markers that open the cited article.
class CitationChips extends StatelessWidget {
  const CitationChips({super.key, required this.numbers, required this.content});

  final List<int> numbers;
  final AnalysisContent content;

  @override
  Widget build(BuildContext context) {
    if (numbers.isEmpty) {
      return const Text('No citation', style: TextStyle(color: AppColors.error, fontSize: 12));
    }
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final n in numbers)
          Builder(builder: (context) {
            final c = content.citation(n);
            return Semantics(
              button: true,
              label: c == null ? 'Citation $n' : 'Citation $n, ${c.publisher}: ${c.title}',
              child: InkWell(
                borderRadius: BorderRadius.circular(8),
                onTap: c == null ? null : () => openExternal(context, c.url),
                child: Container(
                  // No `alignment` here: an aligned Container expands to the full
                  // width, which stretched every chip across the card.
                  constraints: const BoxConstraints(minWidth: 40, minHeight: 32),
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                  decoration: BoxDecoration(
                    color: AppColors.tealLight,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    c == null ? '[$n]' : '[$n] ${publisherAbbrev(c.publisher)}',
                    style: const TextStyle(color: AppColors.blueLight, fontWeight: FontWeight.w700, fontSize: 12.5),
                  ),
                ),
              ),
            );
          }),
      ],
    );
  }
}

class InfoBanner extends StatelessWidget {
  const InfoBanner(this.text, {super.key, this.icon = Icons.info_outline, this.color = AppColors.uncertain, this.background = AppColors.uncertainLight});

  final String text;
  final IconData icon;
  final Color color;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(12)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: color),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: TextStyle(color: color, height: 1.35, fontSize: 13.5))),
        ],
      ),
    );
  }
}

/// Pulsing placeholder block used while content loads (instead of a spinner).
class Skeleton extends StatefulWidget {
  const Skeleton({super.key, this.width, required this.height, this.radius = 10});

  final double? width;
  final double height;
  final double radius;

  @override
  State<Skeleton> createState() => _SkeletonState();
}

class _SkeletonState extends State<Skeleton> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween(begin: 0.45, end: 1.0).animate(_pulse),
      child: Container(
        width: widget.width,
        height: widget.height,
        decoration: BoxDecoration(color: AppColors.cardRaised, borderRadius: BorderRadius.circular(widget.radius)),
      ),
    );
  }
}

/// Loading layout shaped like the story list (hero card + rows).
class StoryListSkeleton extends StatelessWidget {
  const StoryListSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Loading stories',
      child: ListView(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        children: [
          const Skeleton(width: 220, height: 14),
          const SizedBox(height: 14),
          const Skeleton(height: 200, radius: 16),
          const SizedBox(height: 14),
          const Skeleton(height: 22),
          const SizedBox(height: 8),
          const Skeleton(width: 240, height: 22),
          const SizedBox(height: 22),
          for (var i = 0; i < 3; i++) ...[
            const Row(
              children: [
                Skeleton(width: 104, height: 80),
                SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Skeleton(width: 70, height: 12),
                      SizedBox(height: 8),
                      Skeleton(height: 16),
                      SizedBox(height: 6),
                      Skeleton(width: 150, height: 16),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
          ],
        ],
      ),
    );
  }
}

/// Banner shown when content comes from the offline copy.
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key, required this.savedAt, this.onRetry});

  final DateTime savedAt;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 4, 10),
      decoration: BoxDecoration(
        color: AppColors.disagreeSoft,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.disagree.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, color: AppColors.disagree, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Offline · showing content saved ${relativeTime(savedAt).toLowerCase()}. '
              'Expired news is hidden. Publisher pages need a connection.',
              style: const TextStyle(color: AppColors.textSubtle, fontSize: 12.5, height: 1.35),
            ),
          ),
          if (onRetry != null) TextButton(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}
