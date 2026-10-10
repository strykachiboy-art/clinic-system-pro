import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:clinic_system_pro/core/config/backend_config.dart';
import 'package:clinic_system_pro/core/networking/api_client.dart';
import 'package:clinic_system_pro/core/networking/api_exception.dart';
import 'package:clinic_system_pro/features/auth/data/auth_remote_data_source.dart';

const refreshToken = 'refresh-token-example';
const accessToken = 'access-token-example';

BackendConfig testConfig() => const BackendConfig(
  baseUrl: 'http://127.0.0.1:5000',
  allowInsecureHttp: true,
);

Map<String, dynamic> refreshedEnvelope() => {
  'success': true,
  'data': {
    'access_token': 'rotated-access-token',
    'refresh_token': 'rotated-refresh-token',
    'user_id': 42,
    'role': 'DOCTOR',
    'clinic_context_id': null,
  },
};

void main() {
  group('AuthRemoteDataSource refresh and logout', () {
    test(
      'refresh sends refresh token as bearer and parses rotated tokens',
      () async {
        final mock = MockClient((request) async {
          expect(request.method, 'POST');
          expect(
            request.url,
            Uri.parse('http://127.0.0.1:5000/api/v1/auth/refresh'),
          );
          expect(request.headers['authorization'], 'Bearer $refreshToken');
          expect(request.headers['accept'], 'application/json');
          expect(request.headers['content-type'], contains('application/json'));
          expect(jsonDecode(request.body), <String, dynamic>{});

          return http.Response(jsonEncode(refreshedEnvelope()), 200);
        });
        addTearDown(mock.close);

        final source = AuthRemoteDataSource(
          apiClient: ApiClient(config: testConfig(), client: mock),
        );

        final result = await source.refresh(refreshToken: refreshToken);

        expect(result.accessToken, 'rotated-access-token');
        expect(result.refreshToken, 'rotated-refresh-token');
        expect(result.userId, 42);
      },
    );

    test('logout sends access bearer and refresh token in the body', () async {
      final mock = MockClient((request) async {
        expect(request.method, 'POST');
        expect(
          request.url,
          Uri.parse('http://127.0.0.1:5000/api/v1/auth/logout'),
        );
        expect(request.headers['authorization'], 'Bearer $accessToken');
        expect(jsonDecode(request.body), {'refresh_token': refreshToken});

        return http.Response('{"success":true,"message":"Logged out"}', 200);
      });
      addTearDown(mock.close);

      final source = AuthRemoteDataSource(
        apiClient: ApiClient(config: testConfig(), client: mock),
      );

      await expectLater(
        source.logout(accessToken: accessToken, refreshToken: refreshToken),
        completes,
      );
    });

    test('rejects an empty refresh token without making a request', () async {
      final mock = MockClient((request) async {
        fail('Refresh request must not be sent.');
      });
      addTearDown(mock.close);

      final source = AuthRemoteDataSource(
        apiClient: ApiClient(config: testConfig(), client: mock),
      );

      await expectLater(
        source.refresh(refreshToken: '  '),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('rejects an empty logout token without making a request', () async {
      final mock = MockClient((request) async {
        fail('Logout request must not be sent.');
      });
      addTearDown(mock.close);

      final source = AuthRemoteDataSource(
        apiClient: ApiClient(config: testConfig(), client: mock),
      );

      await expectLater(
        source.logout(accessToken: accessToken, refreshToken: ''),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('propagates refresh HTTP failures without retrying', () async {
      var requestCount = 0;
      final mock = MockClient((request) async {
        requestCount++;
        return http.Response('{"success":false}', 401);
      });
      addTearDown(mock.close);

      final source = AuthRemoteDataSource(
        apiClient: ApiClient(config: testConfig(), client: mock),
      );

      await expectLater(
        source.refresh(refreshToken: refreshToken),
        throwsA(
          isA<ApiException>()
              .having((error) => error.kind, 'kind', ApiFailureKind.httpStatus)
              .having((error) => error.statusCode, 'statusCode', 401),
        ),
      );

      expect(requestCount, 1);
    });

    test('propagates logout HTTP failures', () async {
      final mock = MockClient((request) async {
        return http.Response('{"success":false}', 401);
      });
      addTearDown(mock.close);

      final source = AuthRemoteDataSource(
        apiClient: ApiClient(config: testConfig(), client: mock),
      );

      await expectLater(
        source.logout(accessToken: accessToken, refreshToken: refreshToken),
        throwsA(
          isA<ApiException>()
              .having((error) => error.kind, 'kind', ApiFailureKind.httpStatus)
              .having((error) => error.statusCode, 'statusCode', 401),
        ),
      );
    });

    test(
      'rejects a 2xx logout response that does not indicate success',
      () async {
        final mock = MockClient((request) async {
          return http.Response('{"success":false}', 200);
        });
        addTearDown(mock.close);

        final source = AuthRemoteDataSource(
          apiClient: ApiClient(config: testConfig(), client: mock),
        );

        await expectLater(
          source.logout(accessToken: accessToken, refreshToken: refreshToken),
          throwsA(isA<FormatException>()),
        );
      },
    );
  });
}
