import 'package:intl/intl.dart';

/// "Just now", "12 min ago", "3 h ago", "Yesterday, 4:12 PM", "Oct 18, 4:12 PM".
String relativeTime(DateTime? t, {DateTime? now}) {
  if (t == null) return 'Unknown time';
  final current = now ?? DateTime.now();
  final diff = current.difference(t);
  if (diff.inMinutes < 1) return 'Just now';
  if (diff.inMinutes < 60) return '${diff.inMinutes} min ago';
  if (diff.inHours < 12) return '${diff.inHours} h ago';
  final today = DateTime(current.year, current.month, current.day);
  final day = DateTime(t.year, t.month, t.day);
  final time = DateFormat.jm().format(t);
  if (day == today) return 'Today, $time';
  if (today.difference(day).inDays == 1) return 'Yesterday, $time';
  return '${DateFormat.MMMd().format(t)}, $time';
}

/// Full readable timestamp in the phone's local time zone.
String fullTime(DateTime? t) => t == null ? 'Unknown' : DateFormat('MMM d, y · h:mm a').format(t);

String publisherAbbrev(String publisher) {
  const known = {
    'BBC News': 'BBC',
    'NPR': 'NPR',
    'Fox News': 'FOX',
    'The Guardian': 'GDN',
    'CBS News': 'CBS',
  };
  if (known.containsKey(publisher)) return known[publisher]!;
  final letters = publisher.replaceAll(RegExp(r'[^A-Za-z]'), '');
  return (letters.length >= 3 ? letters.substring(0, 3) : letters).toUpperCase();
}
