import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:clinic_system_pro/core/security/secure_key_value_storage.dart';
import 'package:clinic_system_pro/features/auth/data/auth_session_store.dart';
import 'package:clinic_system_pro/features/auth/data/models/auth_token_response.dart';

class MemorySecureStorage implements SecureKeyValueStorage {
  MemorySecureStorage({
    Map<String, String>? initialValues,
    this.readFailure,
    this.writeFailure,
    this.deleteFailure,
  }) : values = initialValues ?? <String, String>{};

  final Map<String, String> values;
  final Object? readFailure;
  final Object? writeFailure;
  final Object? deleteFailure;

  @override
  Future<String?> read({required String key}) async {
    if (readFailure != null) {
      throw readFailure!;
    }
    return values[key];
  }

  @override
  Future<void> write({required String key, required String value}) async {
    if (writeFailure != null) {
      throw writeFailure!;
    }
    values[key] = value;
  }

  @override
  Future<void> delete({required String key}) async {
    if (deleteFailure != null) {
      throw deleteFailure!;
    }
    values.remove(key);
  }
}

const testAccessToken = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI0MiJ9.signature';
const testRefreshToken =
    'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI0MiIsInR5cGUiOiJyZWZyZXNoIn0.signature';

AuthTokenResponse validSession() => const AuthTokenResponse(
  accessToken: testAccessToken,
  refreshToken: testRefreshToken,
  userId: 42,
  role: 'DOCTOR',
  clinicContextId: null,
);

Map<String, dynamic> validRecord() => {
  'schema_version': 2,
  'refresh_pending': false,
  'access_token': testAccessToken,
  'refresh_token': testRefreshToken,
  'user_id': 42,
  'role': 'DOCTOR',
  'clinic_context_id': null,
};

AuthSessionStore makeStore(MemorySecureStorage storage) =>
    AuthSessionStore(storage: storage);

void main() {
  group('AuthSessionStore', () {
    test('returns null when no session is stored', () async {
      final store = makeStore(MemorySecureStorage());

      expect(await store.read(), isNull);
    });

    test('round-trips a session in one versioned record', () async {
      final storage = MemorySecureStorage();
      final store = makeStore(storage);

      await store.save(validSession());

      expect(storage.values.keys.toSet(), {AuthSessionStore.storageKey});

      final raw = storage.values[AuthSessionStore.storageKey]!;
      final record = jsonDecode(raw) as Map<String, dynamic>;

      expect(record['schema_version'], 2);
      expect(record['access_token'], testAccessToken);
      expect(record['refresh_token'], testRefreshToken);
      expect(record['refresh_pending'], false);

      final restored = await store.read();

      expect(restored?.accessToken, testAccessToken);
      expect(restored?.refreshToken, testRefreshToken);
      expect(restored?.userId, 42);
      expect(restored?.role, 'DOCTOR');
      expect(restored?.clinicContextId, isNull);
    });

    test('persists refresh-pending in the same secure record', () async {
      final storage = MemorySecureStorage();
      final store = makeStore(storage);

      await store.save(validSession(), refreshPending: true);

      expect(storage.values.keys.toSet(), {AuthSessionStore.storageKey});

      final stored = await store.readRecord();
      expect(stored?.refreshPending, true);
      expect(stored?.session.accessToken, testAccessToken);

      await expectLater(store.read(), throwsA(isA<FormatException>()));

      expect(storage.values.containsKey(AuthSessionStore.storageKey), isTrue);
    });

    test('rejects a malformed refresh-pending marker', () async {
      final record = validRecord()..['refresh_pending'] = 'true';
      final storage = MemorySecureStorage(
        initialValues: {AuthSessionStore.storageKey: jsonEncode(record)},
      );

      await expectLater(
        makeStore(storage).readRecord(),
        throwsA(isA<FormatException>()),
      );
    });
    test('refuses an incomplete token pair before writing', () async {
      final storage = MemorySecureStorage();
      final store = makeStore(storage);
      const invalid = AuthTokenResponse(
        accessToken: 'access-example',
        refreshToken: '',
        userId: 42,
        role: 'DOCTOR',
        clinicContextId: null,
      );

      await expectLater(store.save(invalid), throwsA(isA<FormatException>()));

      expect(storage.values, isEmpty);
    });

    test('refuses malformed token representations before writing', () async {
      final storage = MemorySecureStorage();
      final store = makeStore(storage);
      final invalid = AuthTokenResponse(
        accessToken: 'not-a-jwt',
        refreshToken: testRefreshToken,
        userId: 42,
        role: 'DOCTOR',
        clinicContextId: null,
      );

      await expectLater(store.save(invalid), throwsA(isA<FormatException>()));

      expect(storage.values, isEmpty);
    });
    test('rejects malformed JSON without deleting the record', () async {
      const corrupted = '{"schema_version":';
      final storage = MemorySecureStorage(
        initialValues: {AuthSessionStore.storageKey: corrupted},
      );
      final store = makeStore(storage);

      await expectLater(store.read(), throwsA(isA<FormatException>()));

      expect(storage.values[AuthSessionStore.storageKey], corrupted);
    });

    test('rejects a non-object JSON root', () async {
      final storage = MemorySecureStorage(
        initialValues: {
          AuthSessionStore.storageKey: jsonEncode(['not', 'a', 'record']),
        },
      );

      await expectLater(
        makeStore(storage).read(),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects an unsupported schema version', () async {
      final record = validRecord()..['schema_version'] = 3;
      final storage = MemorySecureStorage(
        initialValues: {AuthSessionStore.storageKey: jsonEncode(record)},
      );

      await expectLater(
        makeStore(storage).read(),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects an incomplete token pair', () async {
      final record = validRecord()..remove('refresh_token');
      final storage = MemorySecureStorage(
        initialValues: {AuthSessionStore.storageKey: jsonEncode(record)},
      );

      await expectLater(
        makeStore(storage).read(),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects empty or whitespace-containing tokens', () async {
      for (final badToken in [
        '',
        'access-example',
        'access token',
        ' refresh-example',
        'first..third',
        'first.second.',
        'first.second.th!rd',
      ]) {
        final record = validRecord()..['access_token'] = badToken;
        final storage = MemorySecureStorage(
          initialValues: {AuthSessionStore.storageKey: jsonEncode(record)},
        );

        await expectLater(
          makeStore(storage).read(),
          throwsA(isA<FormatException>()),
          reason: 'Must reject token representation: $badToken',
        );
      }
    });

    test('rejects invalid identity or clinic context values', () async {
      final invalidRecords = <Map<String, dynamic>>[
        validRecord()..['user_id'] = '42',
        validRecord()..['user_id'] = 0,
        validRecord()..['role'] = ' ',
        validRecord()..['clinic_context_id'] = '7',
        validRecord()..['clinic_context_id'] = -1,
      ];

      for (final record in invalidRecords) {
        final storage = MemorySecureStorage(
          initialValues: {AuthSessionStore.storageKey: jsonEncode(record)},
        );

        await expectLater(
          makeStore(storage).read(),
          throwsA(isA<FormatException>()),
        );
      }
    });

    test('rejects unexpected record fields', () async {
      final record = validRecord()..['extra'] = 'unexpected';
      final storage = MemorySecureStorage(
        initialValues: {AuthSessionStore.storageKey: jsonEncode(record)},
      );

      await expectLater(
        makeStore(storage).read(),
        throwsA(isA<FormatException>()),
      );
    });

    test('propagates storage read failures', () async {
      final store = makeStore(
        MemorySecureStorage(readFailure: StateError('read failed')),
      );

      await expectLater(store.read(), throwsA(isA<StateError>()));
    });

    test('propagates write failures rather than claiming success', () async {
      final storage = MemorySecureStorage(
        writeFailure: StateError('write failed'),
      );

      await expectLater(
        makeStore(storage).save(validSession()),
        throwsA(isA<StateError>()),
      );

      expect(storage.values, isEmpty);
    });

    test('clears only the session key', () async {
      final storage = MemorySecureStorage(
        initialValues: {
          AuthSessionStore.storageKey: jsonEncode(validRecord()),
          'unrelated.preference': 'en',
        },
      );

      await makeStore(storage).clear();

      expect(storage.values.containsKey(AuthSessionStore.storageKey), isFalse);
      expect(storage.values['unrelated.preference'], 'en');
    });

    test('propagates clear failures', () async {
      final store = makeStore(
        MemorySecureStorage(deleteFailure: StateError('delete failed')),
      );

      await expectLater(store.clear(), throwsA(isA<StateError>()));
    });
  });
}
