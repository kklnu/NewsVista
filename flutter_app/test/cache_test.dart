// Offline cache: saved server results are shown when offline, and the 168-hour
// window still applies. JSON here is a hand-written TEST FIXTURE.
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:newsvista/api/api_client.dart';
import 'package:newsvista/api/news_cache.dart';
import 'package:newsvista/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_test.dart' show fakeApi, listJson, detailJson, phone;

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('offline: shows saved stories with a clear banner', (tester) async {
    phone(tester);
    await tester.pumpWidget(NewsVistaApp(api: fakeApi()));
    await tester.pumpAndSettle(); // online load saves a copy
    final offline = ApiClient(baseUrl: 'https://api.test', client: MockClient((_) async => throw http.ClientException('offline')));
    await tester.pumpWidget(NewsVistaApp(api: offline));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Refresh stories'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Offline · showing content saved'), findsOneWidget);
    expect(find.text('Fixture: earthquake strikes off northern Japan'), findsOneWidget);
  });

  test('cache hides stories and articles older than 168 hours', () async {
    final now = DateTime.utc(2026, 10, 20, 12);
    final cache = NewsCache(clock: () => now);
    await cache.save('list:1:all', listJson());
    // Cutoff = (now + 165.5h) - 168h = 09:30Z on Oct 20.
    final later = NewsCache(clock: () => now.add(const Duration(minutes: 168 * 60 - 150)));
    final (list, _) = (await later.load('list:1:all'))!;
    // st_single (09:00Z) has expired; st_quake (10:00Z) is still inside the window.
    expect((list['items'] as List).map((s) => s['id']), ['st_quake']);

    await cache.save('story:st_quake', detailJson());
    // All fixture articles were published 09:00Z, so the whole story has expired.
    expect(await later.load('story:st_quake'), isNull);
    // Before expiry the story is available with its AI analysis.
    final (fresh, _) = (await cache.load('story:st_quake'))!;
    expect((fresh['analysis'] as Map)['status'], 'current');
  });
}
