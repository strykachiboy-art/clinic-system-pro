import 'package:flutter/foundation.dart' show kDebugMode;

/// Central configuration for the existing Clinic System Pro API.
class BackendConfig {
  const BackendConfig({required this.baseUrl, this.allowInsecureHttp = false});

  /// Reads API_BASE_URL at compile time.
  ///
  /// The default is the Android Emulator's address for reaching
  /// a development server running on the host computer.
  factory BackendConfig.fromEnvironment() {
    return BackendConfig(
      baseUrl: const String.fromEnvironment(
        'API_BASE_URL',
        defaultValue: 'http://10.0.2.2:5000',
      ),
      allowInsecureHttp: kDebugMode,
    );
  }

  final String baseUrl;
  final bool allowInsecureHttp;

  Uri get baseUri {
    final uri = Uri.tryParse(baseUrl);

    if (uri == null ||
        !uri.hasAuthority ||
        uri.host.isEmpty ||
        (uri.scheme != 'http' && uri.scheme != 'https') ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw const FormatException(
        'API_BASE_URL must be an HTTP(S) origin without credentials, '
        'a path, query, or fragment.',
      );
    }

    if (uri.scheme == 'http' && !allowInsecureHttp) {
      throw const FormatException(
        'Plain HTTP is permitted only in explicitly configured '
        'development builds. Use HTTPS otherwise.',
      );
    }

    return uri;
  }

  /// Resolves a relative endpoint against the configured API origin.
  Uri endpoint(String path) {
    final normalizedPath = path.trim();

    if (normalizedPath.isEmpty ||
        normalizedPath.startsWith('/') ||
        normalizedPath.startsWith(r'\')) {
      throw ArgumentError.value(
        path,
        'path',
        'Provide a relative endpoint path without a leading slash.',
      );
    }

    final parsedPath = Uri.tryParse(normalizedPath);

    if (parsedPath == null || parsedPath.hasScheme || parsedPath.hasAuthority) {
      throw ArgumentError.value(
        path,
        'path',
        'Endpoint paths must be relative.',
      );
    }

    return baseUri.resolve(normalizedPath);
  }
}
