import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_system_pro/features/auth/data/models/auth_token_response.dart';

Map<String, dynamic> validPayload() => {
  'access_token': 'access-example',
  'refresh_token': 'refresh-example',
  'user_id': 42,
  'role': 'DOCTOR',
  'clinic_context_id': 7,
};

Map<String, dynamic> validEnvelope() => {
  'success': true,
  'data': validPayload(),
};

void main() {
  group('AuthTokenResponse', () {
    test('parses the backend token response contract', () {
      final result = AuthTokenResponse.fromEnvelope(validEnvelope());

      expect(result.accessToken, 'access-example');
      expect(result.refreshToken, 'refresh-example');
      expect(result.userId, 42);
      expect(result.role, 'DOCTOR');
      expect(result.clinicContextId, 7);
    });

    test('accepts a null clinic context', () {
      final envelope = validEnvelope();
      (envelope['data'] as Map<String, dynamic>)['clinic_context_id'] = null;

      final result = AuthTokenResponse.fromEnvelope(envelope);

      expect(result.clinicContextId, isNull);
    });

    test('rejects a response that does not indicate success', () {
      expect(
        () => AuthTokenResponse.fromEnvelope({
          'success': false,
          'data': validPayload(),
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects a missing or non-object data payload', () {
      expect(
        () => AuthTokenResponse.fromEnvelope({'success': true}),
        throwsA(isA<FormatException>()),
      );
      expect(
        () => AuthTokenResponse.fromEnvelope({
          'success': true,
          'data': 'invalid',
        }),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects a missing access token', () {
      final payload = validPayload()..remove('access_token');

      expect(
        () =>
            AuthTokenResponse.fromEnvelope({'success': true, 'data': payload}),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects an empty refresh token', () {
      final payload = validPayload()..['refresh_token'] = '';

      expect(
        () =>
            AuthTokenResponse.fromEnvelope({'success': true, 'data': payload}),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects malformed identity and role fields', () {
      final badUserId = validPayload()..['user_id'] = '42';
      final badRole = validPayload()..['role'] = ' ';

      expect(
        () => AuthTokenResponse.fromEnvelope({
          'success': true,
          'data': badUserId,
        }),
        throwsA(isA<FormatException>()),
      );
      expect(
        () =>
            AuthTokenResponse.fromEnvelope({'success': true, 'data': badRole}),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects a non-integer clinic context', () {
      final payload = validPayload()..['clinic_context_id'] = '7';

      expect(
        () =>
            AuthTokenResponse.fromEnvelope({'success': true, 'data': payload}),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
