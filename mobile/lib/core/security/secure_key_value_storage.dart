import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Platform-backed key-value storage for small secrets such as session tokens.
///
/// This is not a store for clinical records, general application state,
/// or offline database contents.
abstract interface class SecureKeyValueStorage {
  Future<void> write({required String key, required String value});

  Future<String?> read({required String key});

  Future<void> delete({required String key});
}

/// Adapter around the platform secure-storage plugin.
///
/// Android decryption and migration failures are allowed to propagate.
/// Existing stored data must not be silently erased to recover from an error.
class FlutterSecureKeyValueStorage implements SecureKeyValueStorage {
  FlutterSecureKeyValueStorage()
    : _storage = const FlutterSecureStorage(
        aOptions: AndroidOptions(
          resetOnError: false,
          migrateOnAlgorithmChange: true,
        ),
      );

  final FlutterSecureStorage _storage;

  @override
  Future<void> write({required String key, required String value}) {
    return _storage.write(key: key, value: value);
  }

  @override
  Future<String?> read({required String key}) {
    return _storage.read(key: key);
  }

  @override
  Future<void> delete({required String key}) {
    return _storage.delete(key: key);
  }
}
