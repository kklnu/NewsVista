import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'config.dart';
import 'screens/about_screen.dart';
import 'screens/assistant_screen.dart';
import 'screens/home_screen.dart';
import 'screens/search_screen.dart';
import 'theme.dart';

void main() {
  runApp(NewsVistaApp(api: ApiClient()));
}

class NewsVistaApp extends StatelessWidget {
  const NewsVistaApp({super.key, required this.api});

  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: MainShell(api: api),
    );
  }
}

/// Bottom navigation: Home · Search · Ask AI · About.
class MainShell extends StatefulWidget {
  const MainShell({super.key, required this.api});

  final ApiClient api;

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: [
          HomeScreen(api: widget.api, onSearch: () => setState(() => _index = 1)),
          SearchScreen(api: widget.api),
          AssistantScreen(api: widget.api),
          AboutScreen(api: widget.api),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        height: 66,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.search), label: 'Search'),
          NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), selectedIcon: Icon(Icons.auto_awesome), label: 'Ask AI'),
          NavigationDestination(icon: Icon(Icons.info_outline), selectedIcon: Icon(Icons.info), label: 'About'),
        ],
      ),
    );
  }
}
