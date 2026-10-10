import 'package:drift/drift.dart' show driftRuntimeOptions;
import 'package:drift_dev/api/migrations_native.dart';
import 'package:clinic_system_pro/core/storage/app_database.dart';
import 'package:flutter_test/flutter_test.dart';

import 'generated/schema.dart';
import 'generated/schema_v1.dart' as v1;
import 'generated/schema_v2.dart' as v2;

void main() {
  driftRuntimeOptions.dontWarnAboutMultipleDatabases = true;
  late SchemaVerifier verifier;

  setUpAll(() {
    verifier = SchemaVerifier(GeneratedHelper());
  });

  group('simple database migrations', () {
    const versions = GeneratedHelper.versions;

    for (final (i, fromVersion) in versions.indexed) {
      group('from $fromVersion', () {
        for (final toVersion in versions.skip(i + 1)) {
          test('to $toVersion', () async {
            final schema = await verifier.schemaAt(fromVersion);
            final db = AppDatabase(schema.newConnection());

            try {
              await verifier.migrateAndValidate(db, toVersion);
            } finally {
              await db.close();
            }
          });
        }
      });
    }
  });

  test('migration from v1 to v2 preserves metadata', () async {
    const oldAppMetadataData = <v1.AppMetadataData>[
      v1.AppMetadataData(key: 'app.locale', value: 'en'),
    ];

    const expectedNewAppMetadataData = <v2.AppMetadataData>[
      v2.AppMetadataData(key: 'app.locale', value: 'en', updatedAt: null),
    ];

    await verifier.testWithDataIntegrity(
      oldVersion: 1,
      newVersion: 2,
      createOld: v1.DatabaseAtV1.new,
      createNew: v2.DatabaseAtV2.new,
      openTestedDatabase: AppDatabase.new,
      createItems: (batch, oldDb) {
        batch.insertAll(oldDb.appMetadata, oldAppMetadataData);
      },
      validateItems: (newDb) async {
        final rows = await newDb.select(newDb.appMetadata).get();

        expect(rows, expectedNewAppMetadataData);
        expect(rows.single.key, 'app.locale');
        expect(rows.single.value, 'en');
        expect(rows.single.updatedAt, isNull);
      },
    );
  });
}
