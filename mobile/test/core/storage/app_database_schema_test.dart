import 'package:drift_dev/api/migrations_native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_system_pro/core/storage/app_database.dart';

import '../../drift/schema.dart';

void main() {
  test(
    'v1 snapshot opens with AppDatabase and supports metadata access',
    () async {
      final verifier = SchemaVerifier(GeneratedHelper());
      final connection = await verifier.startAt(1);
      final database = AppDatabase(connection);

      addTearDown(database.close);

      expect(database.schemaVersion, 1);
      expect(await database.select(database.appMetadata).get(), isEmpty);

      await database
          .into(database.appMetadata)
          .insert(
            AppMetadataCompanion.insert(key: 'snapshot.check', value: 'v1'),
          );

      final rows = await database.select(database.appMetadata).get();

      expect(rows, hasLength(1));
      expect(rows.single.key, 'snapshot.check');
      expect(rows.single.value, 'v1');
    },
  );
}
