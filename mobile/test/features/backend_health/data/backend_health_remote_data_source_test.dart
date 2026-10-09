import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:clinic_system_pro/core/config/backend_config.dart';
import 'package:clinic_system_pro/core/networking/api_client.dart';
import 'package:clinic_system_pro/core/networking/api_exception.dart';
import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';

BackendHealthRemoteDataSource createDataSource(MockClient client) {
  return BackendHealthRemoteDataSource(
    apiClient: ApiClient(
      config: const BackendConfig(
        baseUrl: 'http://127.0.0.1:5000',
        allowInsecureHttp: true,
      ),
      client: client,
    ),
  );
}

void main() {
  group('BackendHealthRemoteDataSource', () {
    test('requests the existing liveness endpoint', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url, Uri.parse('http://127.0.0.1:5000/health/live'));
        expect(request.headers['accept'], 'application/json');

        return http.Response('{"success":true,"status":"ok"}', 200);
      });
      addTearDown(client.close);

      expect(await createDataSource(client).checkLiveness(), isTrue);
    });

    test(
      'rejects a successful HTTP response with an unexpected payload',
      () async {
        final client = MockClient((request) async {
          return http.Response('{"success":true,"status":"degraded"}', 200);
        });
        addTearDown(client.close);

        expect(await createDataSource(client).checkLiveness(), isFalse);
      },
    );

    test('preserves typed failures for non-success HTTP status', () async {
      final client = MockClient((request) async {
        return http.Response('{"success":false}', 503);
      });
      addTearDown(client.close);

      await expectLater(
        createDataSource(client).checkLiveness(),
        throwsA(
          isA<ApiException>().having(
            (error) => error.kind,
            'kind',
            ApiFailureKind.httpStatus,
          ),
        ),
      );
    });
  });
}
