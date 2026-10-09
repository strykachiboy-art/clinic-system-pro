enum ApiFailureKind { timeout, connection, httpStatus, invalidResponse }

class ApiException implements Exception {
  const ApiException({
    required this.kind,
    required this.message,
    required this.uri,
    this.statusCode,
    this.cause,
  });

  final ApiFailureKind kind;
  final String message;
  final Uri uri;
  final int? statusCode;
  final Object? cause;

  @override
  String toString() {
    final status = statusCode == null ? '' : ', statusCode: $statusCode';
    return 'ApiException(${kind.name}: $message$status)';
  }
}
