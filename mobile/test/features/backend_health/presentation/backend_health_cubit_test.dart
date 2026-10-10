import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:clinic_system_pro/core/config/backend_config.dart';
import 'package:clinic_system_pro/core/networking/api_client.dart';
import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';
import 'package:clinic_system_pro/features/backend_health/presentation/backend_health_cubit.dart';

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

Future<void> expectHealthCheckStates({
  required MockClient client,
  required List<BackendHealthStatus> expectedStatuses,
  String? expectedErrorMessage,
}) async {
  final cubit = BackendHealthCubit(dataSource: createDataSource(client));
  addTearDown(cubit.close);

  // Subscribe before starting the operation so no state transition is missed.
  final statesExpectation = expectLater(
    cubit.stream.map((state) => state.status),
    emitsInOrder(expectedStatuses),
  );

  await cubit.checkHealth();
  await statesExpectation;

  expect(cubit.state.errorMessage, expectedErrorMessage);
}

void main() {
  group('BackendHealthCubit', () {
    test('emits checking then healthy for the expected response', () async {
      final client = MockClient((request) async {
        return http.Response('{"success":true,"status":"ok"}', 200);
      });
      addTearDown(client.close);

      await expectHealthCheckStates(
        client: client,
        expectedStatuses: [
          BackendHealthStatus.checking,
          BackendHealthStatus.healthy,
        ],
      );
    });

    test(
      'emits unhealthy for a successful HTTP response with bad status',
      () async {
        final client = MockClient((request) async {
          return http.Response('{"success":true,"status":"degraded"}', 200);
        });
        addTearDown(client.close);

        await expectHealthCheckStates(
          client: client,
          expectedStatuses: [
            BackendHealthStatus.checking,
            BackendHealthStatus.unhealthy,
          ],
        );
      },
    );

    test('preserves the API error for an unavailable backend', () async {
      final client = MockClient((request) async {
        return http.Response('{"success":false}', 503);
      });
      addTearDown(client.close);

      await expectHealthCheckStates(
        client: client,
        expectedStatuses: [
          BackendHealthStatus.checking,
          BackendHealthStatus.unavailable,
        ],
        expectedErrorMessage: 'The backend returned HTTP 503.',
      );
    });
  });
}
