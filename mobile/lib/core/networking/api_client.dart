import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/backend_config.dart';
import 'api_exception.dart';

/// HTTP boundary for the existing Clinic System Pro backend.
class ApiClient {
  ApiClient({
    required this.config,
    http.Client? client,
    this.requestTimeout = const Duration(seconds: 10),
  }) : _client = client ?? http.Client(),
       _ownsClient = client == null;

  final BackendConfig config;
  final http.Client _client;
  final bool _ownsClient;
  final Duration requestTimeout;

  /// Performs a GET request and requires a JSON object response.
  Future<Map<String, dynamic>> getJson(String path) async {
    final uri = config.endpoint(path);

    late final http.Response response;

    try {
      response = await _client
          .get(
            uri,
            headers: const <String, String>{'Accept': 'application/json'},
          )
          .timeout(requestTimeout);
    } on TimeoutException catch (error) {
      throw ApiException(
        kind: ApiFailureKind.timeout,
        message: 'The backend request timed out.',
        uri: uri,
        cause: error,
      );
    } on http.ClientException catch (error) {
      throw ApiException(
        kind: ApiFailureKind.connection,
        message: 'Unable to connect to the backend.',
        uri: uri,
        cause: error,
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(
        kind: ApiFailureKind.httpStatus,
        message: 'The backend returned HTTP ${response.statusCode}.',
        uri: uri,
        statusCode: response.statusCode,
      );
    }

    final Object? decoded;

    try {
      decoded = jsonDecode(response.body);
    } on FormatException catch (error) {
      throw ApiException(
        kind: ApiFailureKind.invalidResponse,
        message: 'The backend returned invalid JSON.',
        uri: uri,
        cause: error,
      );
    }

    if (decoded is! Map<String, dynamic>) {
      throw ApiException(
        kind: ApiFailureKind.invalidResponse,
        message: 'The backend response must be a JSON object.',
        uri: uri,
      );
    }

    return decoded;
  }

  /// Closes only the internally owned HTTP client.
  void close() {
    if (_ownsClient) {
      _client.close();
    }
  }
}
