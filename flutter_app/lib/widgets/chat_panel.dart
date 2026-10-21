import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../theme.dart';
import '../util/format.dart';

typedef AskFn = Future<AskReply> Function(String question, List<Map<String, String>> history);

class _Turn {
  _Turn.user(this.text)
      : fromUser = true,
        reply = null,
        error = null;
  _Turn.ai(AskReply this.reply)
      : fromUser = false,
        text = reply.answer,
        error = null;
  _Turn.error(this.text, this.error)
      : fromUser = false,
        reply = null;

  final bool fromUser;
  final String text;
  final AskReply? reply;
  final String? error; // the question to retry
}

/// Chat UI for the Ask AI assistant. Every answer comes from the server, which
/// answers from stored coverage; the phone never calls an AI model itself.
class ChatPanel extends StatefulWidget {
  const ChatPanel({
    super.key,
    required this.ask,
    required this.starters,
    required this.onCitation,
    this.scrollController,
    this.emptyTitle = 'Ask about the news',
    this.emptyMessage = '',
  });

  final AskFn ask;
  final List<String> starters;
  final void Function(BuildContext context, AskCitation citation) onCitation;
  final ScrollController? scrollController;
  final String emptyTitle;
  final String emptyMessage;

  @override
  State<ChatPanel> createState() => _ChatPanelState();
}

class _ChatPanelState extends State<ChatPanel> {
  final _input = TextEditingController();
  late final ScrollController _scroll = widget.scrollController ?? ScrollController();
  final List<_Turn> _turns = [];
  bool _waiting = false;

  @override
  void dispose() {
    _input.dispose();
    if (widget.scrollController == null) _scroll.dispose();
    super.dispose();
  }

  List<Map<String, String>> _history() => [
        for (final t in _turns.where((t) => t.error == null))
          {'role': t.fromUser ? 'user' : 'assistant', 'text': t.text},
      ];

  Future<void> _send(String raw) async {
    final q = raw.trim();
    if (q.isEmpty || _waiting) return;
    final history = _history();
    _input.clear();
    setState(() {
      _turns.add(_Turn.user(q));
      _waiting = true;
    });
    _toBottom();
    try {
      final reply = await widget.ask(q, history.length > 8 ? history.sublist(history.length - 8) : history);
      if (mounted) setState(() => _turns.add(_Turn.ai(reply)));
    } on ApiException catch (e) {
      if (mounted) setState(() => _turns.add(_Turn.error(e.message, q)));
    } finally {
      if (mounted) setState(() => _waiting = false);
      _toBottom();
    }
  }

  void _retry(String question) {
    setState(() {
      _turns.removeLast(); // error
      _turns.removeLast(); // the user's question (re-added by _send)
    });
    _send(question);
  }

  void _toBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView(
            controller: _scroll,
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
            children: [
              if (_turns.isEmpty) _empty(),
              for (final t in _turns) _bubble(t),
              if (_waiting) const _Typing(),
            ],
          ),
        ),
        _inputBar(),
      ],
    );
  }

  Widget _empty() {
    return Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.emptyTitle, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          if (widget.emptyMessage.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(widget.emptyMessage, style: const TextStyle(color: AppColors.textMuted, height: 1.4)),
          ],
          const SizedBox(height: 14),
          const Text('Try asking', style: TextStyle(color: AppColors.textMuted, fontSize: 12.5)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [for (final s in widget.starters) _suggestion(s)]),
        ],
      ),
    );
  }

  Widget _suggestion(String text) {
    // Custom pill instead of ActionChip so long questions wrap instead of being cut off.
    return Material(
      color: AppColors.aiSoft,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: AppColors.ai.withValues(alpha: 0.5)),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: _waiting ? null : () => _send(text),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: Text(text, style: const TextStyle(color: AppColors.aiLight, fontWeight: FontWeight.w600, height: 1.3)),
          ),
        ),
      ),
    );
  }

  Widget _bubble(_Turn t) {
    if (t.fromUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(top: 10, left: 48),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: const BoxDecoration(
            color: AppColors.blue,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(16), topRight: Radius.circular(16), bottomLeft: Radius.circular(16)),
          ),
          child: Text(t.text, style: const TextStyle(color: Colors.white, height: 1.35)),
        ),
      );
    }
    if (t.error != null) {
      return Container(
        margin: const EdgeInsets.only(top: 10, right: 32),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: AppColors.errorSoft, borderRadius: BorderRadius.circular(14)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t.text, style: const TextStyle(color: AppColors.error, height: 1.35)),
            TextButton.icon(onPressed: () => _retry(t.error!), icon: const Icon(Icons.refresh), label: const Text('Try again')),
          ],
        ),
      );
    }
    final r = t.reply!;
    final isAi = r.label == 'AI-generated';
    return Container(
      margin: const EdgeInsets.only(top: 10, right: 20),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.card,
        border: Border.all(color: AppColors.border),
        borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(16), topRight: Radius.circular(16), bottomRight: Radius.circular(16)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(isAi ? Icons.auto_awesome : Icons.info_outline, size: 15, color: AppColors.aiLight),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  isAi ? 'AI-generated${r.cached ? ' · saved answer' : ''}' : 'NewsVista',
                  style: const TextStyle(color: AppColors.aiLight, fontSize: 12, fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(r.answer, style: const TextStyle(height: 1.45, color: AppColors.textSubtle, fontSize: 15)),
          if (r.flag != null) ...[
            const SizedBox(height: 8),
            Text(r.flag!, style: const TextStyle(color: AppColors.disagree, fontSize: 12.5)),
          ],
          if (r.citations.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(spacing: 6, runSpacing: 6, children: [for (final c in r.citations) _citation(c)]),
          ],
          if (r.generalContext != null) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: AppColors.uncertainSoft, borderRadius: BorderRadius.circular(10)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(r.generalContextLabel,
                      style: const TextStyle(color: AppColors.blueLight, fontSize: 11.5, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(r.generalContext!, style: const TextStyle(color: AppColors.textSubtle, fontSize: 13.5, height: 1.4)),
                ],
              ),
            ),
          ],
          if (r.followUps.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(spacing: 8, runSpacing: 8, children: [for (final f in r.followUps) _suggestion(f)]),
          ],
        ],
      ),
    );
  }

  Widget _citation(AskCitation c) {
    final isStory = c.kind == 'story';
    final label = isStory
        ? '[${c.number}] ${c.title.length > 38 ? '${c.title.substring(0, 38)}…' : c.title}'
        : '[${c.number}] ${c.kind == 'background' ? c.title : publisherAbbrev(c.publisher)}';
    return Semantics(
      button: true,
      label: 'Source ${c.number}: ${c.publisher} ${c.title}',
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => widget.onCitation(context, c),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(color: AppColors.blueSoft, borderRadius: BorderRadius.circular(8)),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(isStory ? Icons.article_outlined : (c.kind == 'background' ? Icons.menu_book : Icons.open_in_new),
                  size: 14, color: AppColors.blueLight),
              const SizedBox(width: 5),
              Flexible(
                child: Text(label,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: AppColors.blueLight, fontWeight: FontWeight.w700, fontSize: 12.5)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _inputBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      decoration: const BoxDecoration(
        color: AppColors.navy,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _input,
                enabled: !_waiting,
                minLines: 1,
                maxLines: 4,
                maxLength: 300,
                textInputAction: TextInputAction.send,
                onSubmitted: _send,
                decoration: const InputDecoration(
                  hintText: 'Ask a question…',
                  counterText: '',
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              tooltip: 'Send',
              onPressed: _waiting ? null : () => _send(_input.text),
              style: IconButton.styleFrom(backgroundColor: AppColors.ai, minimumSize: const Size(48, 48)),
              icon: const Icon(Icons.send, color: Colors.white),
            ),
          ],
        ),
      ),
    );
  }
}

class _Typing extends StatelessWidget {
  const _Typing();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(top: 12),
      child: Row(
        children: [
          SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.aiLight)),
          SizedBox(width: 10),
          Text('NewsVista AI is reading the coverage…', style: TextStyle(color: AppColors.textMuted)),
        ],
      ),
    );
  }
}

/// Small header shown above the chat (title + honesty note).
class ChatHeader extends StatelessWidget {
  const ChatHeader({super.key, required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 10),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: [AppColors.blue, AppColors.ai]),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
                Text(subtitle, style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
