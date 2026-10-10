import 'dart:convert';

import '../../../core/security/secure_key_value_storage.dart';
import 'models/auth_token_response.dart';

/// Persists authentication session metadata as one versioned secure record.
///
/// This validates record structure, not JWT signatures or token authenticity.
/// The backend remains authoritative when a token is presented for use.
class AuthSessionStore {
  const AuthSessionStore({required SecureKeyValueStorage storage})
    : this._(storage);

  const AuthSessionStore._(this._storage);

  final SecureKeyValueStorage _storage;

  static const String storageKey = 'clinic_system.auth_session';
  static const int currentSchemaVersion = 1;

  static const Set<String> _recordKeys = {
    'schema_version',
    'access_token',
    'refresh_token',
    'user_id',
    'role',
    'clinic_context_id',
  };

  /// Validates the complete session before writing a single secure-storage key.
  Future<void> save(AuthTokenResponse session) async {
    final record = <String, dynamic>{
      'schema_version': currentSchemaVersion,
      'access_token': session.accessToken,
      'refresh_token': session.refreshToken,
      'user_id': session.userId,
      'role': session.role,
      'clinic_context_id': session.clinicContextId,
    };

    // Validate caller-constructed instances too; constructors alone do not
    // guarantee that a response model was created from validated JSON.
    _parseRecord(record);

    await _storage.write(key: storageKey, value: jsonEncode(record));
  }

  /// Returns null when no session exists.
  ///
  /// A corrupt or unsupported record throws FormatException and is not
  /// silently deleted or treated as a valid session.
  Future<AuthTokenResponse?> read() async {
    final raw = await _storage.read(key: storageKey);
    if (raw == null) {
      return null;
    }

    final Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      throw const FormatException(
        'Stored authentication session contains invalid JSON.',
      );
    }

    if (decoded is! Map<String, dynamic>) {
      throw const FormatException(
        'Stored authentication session must be a JSON object.',
      );
    }

    return _parseRecord(decoded);
  }

  /// Deletes only this session record. Storage failures propagate.
  Future<void> clear() {
    return _storage.delete(key: storageKey);
  }

  AuthTokenResponse _parseRecord(Map<String, dynamic> record) {
    final keys = record.keys.toSet();
    if (keys.length != _recordKeys.length || !keys.containsAll(_recordKeys)) {
      throw const FormatException(
        'Stored authentication session fields are incomplete or unexpected.',
      );
    }

    final Object? version = record['schema_version'];
    if (version is! int || version != currentSchemaVersion) {
      throw const FormatException(
        'Stored authentication session version is unsupported.',
      );
    }

    final session = AuthTokenResponse.fromJson({
      'access_token': record['access_token'],
      'refresh_token': record['refresh_token'],
      'user_id': record['user_id'],
      'role': record['role'],
      'clinic_context_id': record['clinic_context_id'],
    });

    if (!_isCompactToken(session.accessToken) ||
        !_isCompactToken(session.refreshToken)) {
      throw const FormatException(
        'Stored authentication session contains an invalid token representation.',
      );
    }

    final clinicContextId = session.clinicContextId;
    if (clinicContextId != null && clinicContextId <= 0) {
      throw const FormatException(
        'Stored clinic context ID must be positive or null.',
      );
    }

    return session;
  }

  bool _isCompactToken(String token) {
    // Require three non-empty Base64URL segments. This checks representation
    // only, not signature validity, expiry, issuer, or revocation status.
    final segments = token.split('.');
    if (segments.length != 3) {
      return false;
    }

    final base64UrlSegment = RegExp(r'^[A-Za-z0-9_-]+$');
    return segments.every(base64UrlSegment.hasMatch);
  }
}
