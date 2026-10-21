/// App-wide constants.
///
/// The API URL is supplied at build time so no server address or secret is
/// hard-coded in source:
///   flutter build apk --release --dart-define=API_BASE_URL=https://your-api.onrender.com
class AppConfig {
  static const appName = 'NewsVista';
  static const tagline = 'One story. Multiple sources. A clearer perspective.';
  static const version = '1.0.0';

  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://newsvista-api.onrender.com',
  );

  /// Free hosting can take up to a minute to wake from sleep.
  static const requestTimeout = Duration(seconds: 75);
  static const pageSize = 30;

  static const feedbackEmail = String.fromEnvironment('FEEDBACK_EMAIL', defaultValue: '');
}
