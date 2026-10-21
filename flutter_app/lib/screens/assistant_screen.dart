import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../util/open_link.dart';
import '../widgets/chat_panel.dart';
import 'story_screen.dart';

/// Opens what an Ask AI citation points to: a story inside the app, or a
/// publisher / reference page in the browser.
void openAskCitation(BuildContext context, ApiClient api, AskCitation c) {
  if (c.storyId != null) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => StoryScreen(api: api, storyId: c.storyId!, initialHeadline: c.title)),
    );
  } else if (c.url != null) {
    openExternal(context, c.url!);
  }
}

/// "Ask AI" tab: questions about any news from the last 7 days.
class AssistantScreen extends StatefulWidget {
  const AssistantScreen({super.key, required this.api});

  final ApiClient api;

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends State<AssistantScreen> {
  List<String> _starters = const ["What are today's top stories?", "What's the biggest world news this week?"];

  @override
  void initState() {
    super.initState();
    _loadStarters();
  }

  /// Suggest questions about stories that are actually in the news right now.
  Future<void> _loadStarters() async {
    try {
      final res = await widget.api.fetchStories(limit: 3, minPublishers: 2);
      if (!mounted || res.items.isEmpty) return;
      setState(() {
        _starters = [
          "What are today's top stories?",
          for (final s in res.items.take(2))
            'Explain: ${s.headline.length > 60 ? '${s.headline.substring(0, 60)}…' : s.headline}',
        ];
      });
    } on ApiException {
      // Keep the generic suggestions.
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ask AI', style: TextStyle(fontWeight: FontWeight.w800))),
      body: SafeArea(
        child: Column(
          children: [
            const ChatHeader(
              title: 'NewsVista Assistant',
              subtitle: 'Answers from stories collected in the last 7 days, with sources.',
            ),
            Expanded(
              child: ChatPanel(
                ask: widget.api.askNews,
                starters: _starters,
                onCitation: (ctx, c) => openAskCitation(ctx, widget.api, c),
                emptyTitle: 'Ask about the news',
                emptyMessage: 'Ask what happened, who is involved, or how a story developed. Answers are '
                    'written by AI on our server from the stored coverage and link to the stories they use.',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Slide-up "Ask AI about this story" panel used on the story screen.
void showStoryAssistant(BuildContext context, ApiClient api, StoryDetail story) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    showDragHandle: true,
    builder: (sheetContext) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(sheetContext).bottom),
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.88,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        builder: (_, controller) => Column(
          children: [
            ChatHeader(
              title: 'Ask about this story',
              subtitle: 'Answers only from this story\'s ${story.articleCount} article(s) and background.',
            ),
            Expanded(
              child: ChatPanel(
                ask: (q, history) => api.askStory(story.id, q, history),
                scrollController: controller,
                starters: const [
                  'What led up to this?',
                  'Who are the key people involved?',
                  'How do the sources differ?',
                  'What happens next?',
                ],
                onCitation: (ctx, c) => openAskCitation(ctx, api, c),
                emptyTitle: story.headline,
                emptyMessage: 'Questions are answered by AI on our server using only the coverage listed in '
                    'Sources. Background from the AI\'s general knowledge is labelled separately.',
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
