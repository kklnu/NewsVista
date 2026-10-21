import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../config.dart';
import '../theme.dart';
import '../util/format.dart';
import '../widgets/common.dart';

/// About, beta feedback, and the server's collection log (read-only).
class AboutScreen extends StatefulWidget {
  const AboutScreen({super.key, required this.api});

  final ApiClient api;

  @override
  State<AboutScreen> createState() => _AboutScreenState();
}

class _AboutScreenState extends State<AboutScreen> {
  Map<String, dynamic>? _status;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final s = await widget.api.fetchStatus();
      if (mounted) setState(() => _status = s);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final host = Uri.tryParse(AppConfig.apiBaseUrl)?.host ?? AppConfig.apiBaseUrl;
    return Scaffold(
      appBar: AppBar(title: const Text('About NewsVista')),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              Text('${AppConfig.appName} ${AppConfig.version} (beta)',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              const Text(AppConfig.tagline, style: TextStyle(color: AppColors.textSecondary)),
              const SizedBox(height: 16),
              const Text(
                'NewsVista groups coverage of the same event from several publishers into one story. '
                'Our server collects news feeds every hour, keeps only the last 7 days, and generates AI '
                'analysis once per story so every reader sees the same stored result. Publisher and '
                'Wikipedia pages open in your browser and need an internet connection.',
                style: TextStyle(height: 1.45),
              ),
              const SizedBox(height: 16),
              InfoBanner(
                AppConfig.feedbackEmail.isEmpty
                    ? 'Beta feedback: report problems to the NewsVista team (see the project README for the issue tracker).'
                    : 'Beta feedback: email ${AppConfig.feedbackEmail} with the story headline and what went wrong.',
                icon: Icons.bug_report_outlined,
              ),
              SectionTitle('Server collection log', icon: Icons.dns_outlined),
              Text('API: $host', style: const TextStyle(color: AppColors.textSecondary, fontSize: 12.5)),
              const SizedBox(height: 8),
              if (_error != null)
                InfoBanner(_error!, icon: Icons.cloud_off, color: AppColors.error, background: AppColors.errorLight)
              else if (_status == null)
                const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))
              else
                ..._runs(),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _runs() {
    final runs = (_status!['runs'] as List? ?? const []).cast<Map<String, dynamic>>();
    final last = DateTime.tryParse(_status!['last_successful_collection_at'] as String? ?? '')?.toLocal();
    final ai = _status!['ai'] as Map<String, dynamic>? ?? const {};
    return [
      Text('Last successful collection: ${fullTime(last)}', style: const TextStyle(fontWeight: FontWeight.w600)),
      const SizedBox(height: 4),
      Text('AI model: ${ai['model'] ?? '—'} · stored analyses: ${ai['analyses_ok'] ?? 0}',
          style: const TextStyle(color: AppColors.textSecondary, fontSize: 12.5)),
      const SizedBox(height: 8),
      for (final r in runs.take(12))
        Card(
          margin: const EdgeInsets.only(bottom: 8),
          child: ListTile(
            dense: true,
            leading: Icon(
              r['status'] == 'success' ? Icons.check_circle : (r['status'] == 'partial' ? Icons.warning_amber : Icons.error),
              color: r['status'] == 'success' ? AppColors.agree : (r['status'] == 'partial' ? AppColors.disagree : AppColors.error),
            ),
            title: Text('#${r['id']} · ${r['trigger']} · ${r['status']}'),
            subtitle: Text(
              '${fullTime(DateTime.tryParse(r['started_at'] as String? ?? '')?.toLocal())} · '
              '${r['articles_new']} new, ${r['articles_expired']} expired, ${r['ai_generated']} AI',
            ),
          ),
        ),
    ];
  }
}
