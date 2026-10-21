// Widget tests with a mocked HTTP client. The JSON below is a hand-written
// TEST FIXTURE shaped like the real API, not live news.
import 'dart:convert';

import 'package:flutter/material.dart';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:newsvista/api/api_client.dart';
import 'package:newsvista/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> listJson() => {
      'served_at': '2026-10-20T12:00:00Z',
      'window_hours': 168,
      'last_successful_collection_at': '2026-10-20T11:07:00Z',
      'total': 2,
      'items': [
        {
          'id': 'st_quake',
          'headline': 'Fixture: earthquake strikes off northern Japan',
          'latest_published_at': '2026-10-20T10:00:00Z',
          'updated_at': '2026-10-20T11:07:00Z',
          'publisher_count': 3,
          'article_count': 3,
          'publishers': ['BBC News', 'Fox News', 'NPR'],
          'ai_status': 'current',
        },
        {
          'id': 'st_single',
          'headline': 'Fixture: council approves park budget',
          'latest_published_at': '2026-10-20T09:00:00Z',
          'updated_at': '2026-10-20T11:07:00Z',
          'publisher_count': 1,
          'article_count': 1,
          'publishers': ['NPR'],
          'ai_status': 'pending',
        },
      ],
    };

Map<String, dynamic> article(String id, String pub) => {
      'id': id,
      'title': '$pub fixture headline',
      'url': 'https://example.test/$id',
      'published_at': '2026-10-20T09:00:00Z',
      'excerpt': 'Fixture excerpt.',
      'excerpt_label': 'Excerpt from $pub',
    };

Map<String, dynamic> detailJson({bool withAi = true, bool perspectives = true}) => {
      'id': 'st_quake',
      'headline': 'Fixture: earthquake strikes off northern Japan',
      'created_at': '2026-10-20T10:00:00Z',
      'updated_at': '2026-10-20T11:07:00Z',
      'latest_published_at': '2026-10-20T10:00:00Z',
      'publisher_count': 2,
      'article_count': 3,
      'overview': withAi
          ? {'kind': 'ai_generated', 'label': 'AI-generated overview', 'text': 'AI fixture overview.', 'generated_at': '2026-10-20T11:08:00Z'}
          : {'kind': 'publisher_excerpt', 'label': 'Publisher excerpt — NPR (original wording)', 'text': 'Fixture excerpt.', 'generated_at': null},
      'publishers': [
        {'publisher': 'BBC News', 'article_count': 2, 'articles': [article('b1', 'BBC News'), article('b2', 'BBC News')]},
        {'publisher': 'NPR', 'article_count': 1, 'articles': [article('n1', 'NPR')]},
      ],
      'background': {'status': 'none', 'message': 'No background resource available', 'links': []},
      'analysis': {
        'label': 'AI-generated',
        'status': withAi ? 'current' : 'failed',
        'status_message': withAi ? 'Up to date' : 'AI analysis is temporarily unavailable.',
        'analysis_id': 7,
        'version': 1,
        'generated_at': '2026-10-20T11:08:00Z',
        'model': 'fixture-model',
        'content': withAi
            ? {
                'overview': {'text': 'AI fixture overview.', 'citations': [1, 2], 'flag': null},
                'agreements': [
                  {'text': 'Both report the quake.', 'citations': [1, 2]}
                ],
                'disagreements': [],
                'uncertainties': [],
                'perspectives_status': perspectives ? 'supported' : 'insufficient_evidence',
                'perspectives_message': perspectives ? null : 'Insufficient evidence for distinct perspectives.',
                'perspectives': perspectives
                    ? [
                        {'id': 'p1', 'name': 'Officials: caution', 'summary': 'Officials urged caution.', 'caveats': 'Limited detail.', 'claims': [{'text': 'Officials warned of aftershocks.', 'citations': [1]}]},
                        {'id': 'p2', 'name': 'Residents: concern', 'summary': 'Residents worried.', 'caveats': '', 'claims': [{'text': 'Residents left the coast.', 'citations': [2]}]},
                      ]
                    : [],
                'limitations': ['Feed excerpts only.'],
                'input_scope': {'kind': 'feed_excerpts', 'article_count': 2, 'publisher_count': 2, 'disclosure': 'Input scope: only short RSS feed excerpts.'},
                'needs_review': false,
                'review_notes': [],
                'citations': [
                  {'number': 1, 'article_id': 'b1', 'publisher': 'BBC News', 'title': 'BBC fixture', 'url': 'https://example.test/b1', 'published_at': '2026-10-20T09:00:00Z'},
                  {'number': 2, 'article_id': 'n1', 'publisher': 'NPR', 'title': 'NPR fixture', 'url': 'https://example.test/n1', 'published_at': '2026-10-20T09:00:00Z'},
                ],
              }
            : null,
      },
      'window_hours': 168,
      'last_successful_collection_at': '2026-10-20T11:07:00Z',
      'served_at': '2026-10-20T12:00:00Z',
    };

Map<String, dynamic> askJson(String question, {required bool story}) => {
      'label': 'AI-generated',
      'answer': 'Fixture answer to: $question',
      'citations': [
        story
            ? {'number': 1, 'label': 'A1', 'kind': 'article', 'title': 'BBC fixture', 'publisher': 'BBC News', 'url': 'https://example.test/b1'}
            : {'number': 1, 'label': 'S1', 'kind': 'story', 'title': 'Fixture: earthquake strikes off northern Japan', 'publisher': 'BBC News', 'story_id': 'st_quake'}
      ],
      'general_context': 'Fixture general background.',
      'general_context_label': 'General background from the AI model — not from the collected coverage',
      'follow_up_questions': ['Fixture follow-up?'],
      'flag': null,
      'model': 'fixture-model',
      'cached': false,
      'generated_at': '2026-10-21T12:00:00Z',
    };

ApiClient fakeApi({Map<String, dynamic>? detail, bool failList = false, List<String>? log}) {
  return ApiClient(
    baseUrl: 'https://api.test',
    client: MockClient((req) async {
      log?.add('${req.method} ${req.url.path}'.replaceFirst('GET ', ''));
      if (req.method == 'POST' && req.url.path.endsWith('/ask')) {
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        return http.Response.bytes(utf8.encode(jsonEncode(askJson(body['question'] as String, story: req.url.path != '/ask'))), 200);
      }
      if (req.url.path == '/stories') {
        if (failList) return http.Response('oops', 500);
        return http.Response.bytes(utf8.encode(jsonEncode(listJson())), 200);
      }
      if (req.url.path.startsWith('/stories/')) {
        return http.Response.bytes(utf8.encode(jsonEncode(detail ?? detailJson())), 200);
      }
      return http.Response('not found', 404);
    }),
  );
}

final scrollable = find.byType(Scrollable).first;

Future<void> openQuakeStory(WidgetTester tester) async {
  await tester.tap(find.text('Fixture: earthquake strikes off northern Japan'));
  await tester.pumpAndSettle();
}

/// Pixel-like phone screen (412 x 915 logical pixels).
void phone(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 1080 / 412;
  addTearDown(tester.view.reset);
}

Future<void> openTab(WidgetTester tester, String name) async {
  await tester.ensureVisible(find.text(name));
  await tester.pumpAndSettle();
  await tester.tap(find.text(name));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets('story list shows hero + rows with distinct-publisher counts', (tester) async {
    phone(tester);
    await tester.pumpWidget(NewsVistaApp(api: fakeApi()));
    await tester.pumpAndSettle();
    expect(find.text('Fixture: earthquake strikes off northern Japan'), findsOneWidget);
    expect(find.text('TOP STORY'), findsOneWidget);
    expect(find.text('3 sources'), findsOneWidget);
    expect(find.text('1 source'), findsOneWidget);
    expect(find.textContaining('Updated'), findsOneWidget);
  });

  testWidgets('list error shows readable message and retry', (tester) async {
    phone(tester);
    await tester.pumpWidget(NewsVistaApp(api: fakeApi(failList: true)));
    await tester.pumpAndSettle();
    expect(find.text('Could not load stories'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('tabs: only covering publishers, chooser, no-background message', (tester) async {
    phone(tester);
    await tester.pumpWidget(NewsVistaApp(api: fakeApi()));
    await tester.pumpAndSettle();
    await openQuakeStory(tester);
    expect(find.text('Quick Summary'), findsOneWidget);
    expect(find.textContaining('AI-generated'), findsWidgets);
    await openTab(tester, 'Sources');
    expect(find.text('BBC News'), findsOneWidget);
    expect(find.text('NPR fixture headline'), findsOneWidget); // single NPR article opens directly
    expect(find.text('Fox News'), findsNothing);
    expect(find.textContaining('tap to choose'), findsOneWidget); // BBC has two articles
    await openTab(tester, 'Background');
    expect(find.text('No background resource available'), findsOneWidget);
  });

  testWidgets('AI analysis tab and perspective navigation with back', (tester) async {
    phone(tester);
    final log = <String>[];
    await tester.pumpWidget(NewsVistaApp(api: fakeApi(log: log)));
    await tester.pumpAndSettle();
    await openQuakeStory(tester);
    await openTab(tester, 'AI Analysis');
    expect(find.text('AI fixture overview.'), findsOneWidget);
    expect(find.text('Agreement'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Officials: caution'), 200, scrollable: scrollable);
    await tester.drag(scrollable, const Offset(0, -250)); // bring it fully on screen
    await tester.pumpAndSettle();
    await tester.tap(find.text('Officials: caution'));
    await tester.pumpAndSettle();
    expect(find.text('Officials warned of aftershocks.'), findsOneWidget);
    expect(find.text('Supporting coverage'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Officials: caution'), findsOneWidget); // back on the AI tab
    // Opening AI views made no extra server requests (and never any AI call).
    expect(log.where((p) => p.startsWith('/stories/')).length, 1);
  });

  testWidgets('insufficient perspectives are shown honestly', (tester) async {
    phone(tester);
    await tester.pumpWidget(NewsVistaApp(api: fakeApi(detail: detailJson(perspectives: false))));
    await tester.pumpAndSettle();
    await openQuakeStory(tester);
    await openTab(tester, 'AI Analysis');
    await tester.scrollUntilVisible(find.text('Insufficient evidence for distinct perspectives.'), 200, scrollable: scrollable);
    expect(find.text('Insufficient evidence for distinct perspectives.'), findsOneWidget);
  });

  testWidgets('failed AI shows status, not fabricated text', (tester) async {
    phone(tester);
    await tester.pumpWidget(NewsVistaApp(api: fakeApi(detail: detailJson(withAi: false))));
    await tester.pumpAndSettle();
    await openQuakeStory(tester);
    expect(find.text('Publisher excerpt'), findsOneWidget);
    await openTab(tester, 'AI Analysis');
    expect(find.text('AI analysis unavailable'), findsOneWidget);
    expect(find.text('AI fixture overview.'), findsNothing);
  });

  testWidgets('search tab queries the server', (tester) async {
    phone(tester);
    final log = <String>[];
    await tester.pumpWidget(NewsVistaApp(api: fakeApi(log: log)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Search').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'quake');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(find.textContaining('for "quake"'), findsOneWidget);
  });

  testWidgets('Ask AI about a story: server answer with citation and labelled background', (tester) async {
    phone(tester);
    final log = <String>[];
    await tester.pumpWidget(NewsVistaApp(api: fakeApi(log: log)));
    await tester.pumpAndSettle();
    await openQuakeStory(tester);
    await tester.tap(find.text('Ask AI').last);
    await tester.pumpAndSettle();
    expect(find.text('Ask about this story'), findsOneWidget);
    await tester.tap(find.text('What led up to this?'));
    await tester.pumpAndSettle();
    expect(find.text('Fixture answer to: What led up to this?'), findsOneWidget);
    expect(find.text('AI-generated'), findsWidgets); // chat label (story page behind also shows one)
    expect(find.textContaining('not from the collected coverage'), findsOneWidget);
    expect(find.text('[1] BBC'), findsOneWidget);
    expect(log, contains('POST /stories/st_quake/ask'));
  });

  testWidgets('Ask AI tab answers and links to the story', (tester) async {
    phone(tester);
    final log = <String>[];
    await tester.pumpWidget(NewsVistaApp(api: fakeApi(log: log)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ask AI').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'What happened in Japan?');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pumpAndSettle();
    expect(find.text('Fixture answer to: What happened in Japan?'), findsOneWidget);
    expect(log, contains('POST /ask'));
    await tester.tap(find.textContaining('[1] Fixture: earthquake'));
    await tester.pumpAndSettle();
    expect(find.text('Quick Summary'), findsOneWidget); // opened the cited story
  });
}
