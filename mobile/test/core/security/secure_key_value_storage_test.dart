import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:clinic_system_pro/core/security/secure_key_value_storage.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });

  group('FlutterSecureKeyValueStorage', () {
    test('returns null for a key that does not exist', () async {
      final storage = FlutterSecureKeyValueStorage();

      expect(await storage.read(key: 'access_token'), isNull);
    });

    test('writes and reads a stored value', () async {
      final storage = FlutterSecureKeyValueStorage();

      await storage.write(key: 'access_token', value: 'test-token');

      expect(await storage.read(key: 'access_token'), 'test-token');
    });

    test('overwrites the value for an existing key', () async {
      final storage = FlutterSecureKeyValueStorage();

      await storage.write(key: 'access_token', value: 'old-token');
      await storage.write(key: 'access_token', value: 'new-token');

      expect(await storage.read(key: 'access_token'), 'new-token');
    });

    test('deletes only the requested key', () async {
      final storage = FlutterSecureKeyValueStorage();

      await storage.write(key: 'access_token', value: 'access');
      await storage.write(key: 'refresh_token', value: 'refresh');

      await storage.delete(key: 'access_token');

      expect(await storage.read(key: 'access_token'), isNull);
      expect(await storage.read(key: 'refresh_token'), 'refresh');
    });
  });
}
