import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// Opens a publisher or reference page in the phone's browser. Pressing Back in
/// the browser returns to the same NewsVista screen.
Future<void> openExternal(BuildContext context, String url) async {
  final uri = Uri.tryParse(url);
  var opened = false;
  if (uri != null && (uri.scheme == 'https' || uri.scheme == 'http')) {
    try {
      opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      opened = false;
    }
  }
  if (!opened && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Could not open the link. Publisher and reference pages need an internet connection.')),
    );
  }
}
