import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_system_pro/core/config/backend_config.dart';

void main() {
  group('BackendConfig', () {
    test('defaults to the Android Emulator host', () {
      final config = BackendConfig.fromEnvironment();

      expect(config.baseUrl, 'http://10.0.2.2:5000');
      expect(config.baseUri.host, '10.0.2.2');
      expect(config.baseUri.port, 5000);
    });

    test('resolves relative endpoint paths', () {
      const config = BackendConfig(
        baseUrl: 'http://127.0.0.1:5000',
        allowInsecureHttp: true,
      );

      expect(
        config.endpoint('health/live'),
        Uri.parse('http://127.0.0.1:5000/health/live'),
      );
    });

    test('rejects non-HTTP schemes', () {
      const config = BackendConfig(baseUrl: 'ftp://backend.example.test');

      expect(() => config.baseUri, throwsFormatException);
    });

    test('rejects HTTP unless explicitly allowed', () {
      const config = BackendConfig(baseUrl: 'http://backend.example.test');

      expect(() => config.baseUri, throwsFormatException);
    });

    test('rejects endpoint paths with a leading slash', () {
      const config = BackendConfig(baseUrl: 'https://backend.example.test');

      expect(() => config.endpoint('/health/live'), throwsArgumentError);
    });

    test('rejects origins containing a path', () {
      const config = BackendConfig(
        baseUrl: 'https://backend.example.test/api/v1',
      );

      expect(() => config.baseUri, throwsFormatException);
    });
  });
}
