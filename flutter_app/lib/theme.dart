import 'package:flutter/material.dart';

/// Palette from the NewsVista mockup: #0F172A, #2563EB, #8B5CF6, #10B981, #E2E8F0.
class AppColors {
  static const background = Color(0xFF0B1222);
  static const navy = Color(0xFF0F172A);
  static const card = Color(0xFF16213A);
  static const cardRaised = Color(0xFF1C2A47);
  static const border = Color(0xFF26355A);
  static const text = Color(0xFFF1F5F9);
  static const textMuted = Color(0xFF94A3B8);
  static const textSubtle = Color(0xFFE2E8F0);
  static const blue = Color(0xFF2563EB);
  static const blueLight = Color(0xFF60A5FA);
  static const blueSoft = Color(0xFF1E3A6E);
  static const ai = Color(0xFF8B5CF6);
  static const aiLight = Color(0xFFC4B5FD);
  static const aiSoft = Color(0xFF2E2556);
  static const agree = Color(0xFF10B981);
  static const agreeSoft = Color(0xFF0F3B33);
  static const disagree = Color(0xFFF59E0B);
  static const disagreeSoft = Color(0xFF41321A);
  static const uncertain = Color(0xFF3B82F6);
  static const uncertainSoft = Color(0xFF1B2F57);
  static const badge = Color(0xFFDC2626);
  static const error = Color(0xFFF87171);
  static const errorSoft = Color(0xFF3F1D24);

  // Kept for widgets that refer to the older names.
  static const teal = blue;
  static const tealLight = blueSoft;
  static const surface = card;
  static const textSecondary = textMuted;
  static const agreeLight = agreeSoft;
  static const disagreeLight = disagreeSoft;
  static const uncertainLight = uncertainSoft;
  static const errorLight = errorSoft;
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: AppColors.blue,
    brightness: Brightness.dark,
    primary: AppColors.blue,
    onPrimary: Colors.white,
    secondary: AppColors.ai,
    surface: AppColors.card,
    onSurface: AppColors.text,
  );
  final base = ThemeData(colorScheme: scheme, useMaterial3: true, brightness: Brightness.dark, fontFamily: 'Inter');
  return base.copyWith(
    scaffoldBackgroundColor: AppColors.background,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.background,
      foregroundColor: AppColors.text,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(fontFamily: 'Inter', fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.text),
    ),
    cardTheme: CardThemeData(
      color: AppColors.card,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppColors.border),
      ),
    ),
    textTheme: base.textTheme.apply(bodyColor: AppColors.text, displayColor: AppColors.text),
    dividerColor: AppColors.border,
    tabBarTheme: const TabBarThemeData(
      labelColor: Colors.white,
      unselectedLabelColor: AppColors.textMuted,
      indicatorSize: TabBarIndicatorSize.tab,
      dividerColor: Colors.transparent,
      labelStyle: TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.navy,
      indicatorColor: AppColors.blueSoft,
      labelTextStyle: WidgetStateProperty.all(const TextStyle(fontSize: 12, color: AppColors.textSubtle)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        backgroundColor: AppColors.blue,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 48),
        foregroundColor: AppColors.text,
        side: const BorderSide(color: AppColors.border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.card,
      hintStyle: const TextStyle(color: AppColors.textMuted),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: AppColors.blueLight),
  );
}
