import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:clinic_system_pro/core/security/secure_key_value_storage.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'secure storage writes, reads, overwrites, and deletes on Android',
    (_) async {
      final storage = FlutterSecureKeyValueStorage();
      final observer = FlutterSecureKeyValueStorage();

      final key =
          '__clinic_system_pro_secure_storage_test_${DateTime.now().microsecondsSinceEpoch}';

      addTearDown(() async {
        await storage.delete(key: key);
      });

      await storage.write(key: key, value: 'first-test-value');

      expect(await storage.read(key: key), 'first-test-value');
      expect(await observer.read(key: key), 'first-test-value');

      await storage.write(key: key, value: 'replacement-test-value');

      expect(await observer.read(key: key), 'replacement-test-value');

      await storage.delete(key: key);

      expect(await observer.read(key: key), isNull);
    },
  );
}
