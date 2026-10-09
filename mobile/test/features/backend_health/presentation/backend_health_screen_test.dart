import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:clinic_system_pro/core/config/backend_config.dart';
import 'package:clinic_system_pro/core/networking/api_client.dart';
import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';
import 'package:clinic_system_pro/features/backend_health/presentation/backend_health_screen.dart';

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
  group('BackendHealthScreen', () {
    testWidgets('shows healthy status for the expected response', (
      tester,
    ) async {
      final client = MockClient((request) async {
        return http.Response('{"success":true,"status":"ok"}', 200);
      });
      addTearDown(client.close);

      await tester.pumpWidget(
        MaterialApp(
          home: BackendHealthScreen(dataSource: createDataSource(client)),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Backend reachable'), findsOneWidget);
      expect(find.text('Check again'), findsOneWidget);
    });

    testWidgets('shows an error and retries successfully', (tester) async {
      var requestCount = 0;

      final client = MockClient((request) async {
        requestCount++;

        if (requestCount == 1) {
          return http.Response('{"success":false}', 503);
        }

        return http.Response('{"success":true,"status":"ok"}', 200);
      });
      addTearDown(client.close);

      await tester.pumpWidget(
        MaterialApp(
          home: BackendHealthScreen(dataSource: createDataSource(client)),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Backend unavailable'), findsOneWidget);
      expect(find.text('The backend returned HTTP 503.'), findsOneWidget);

      await tester.tap(find.text('Check again'));
      await tester.pumpAndSettle();

      expect(find.text('Backend reachable'), findsOneWidget);
      expect(requestCount, 2);
    });
  });
}
