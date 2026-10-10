import 'package:drift_dev/api/migrations_native.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../drift/app_database/generated/schema.dart';
import '../../drift/app_database/generated/schema_v1.dart' as v1;

void main() {
  test('historical v1 snapshot can initialize and use metadata', () async {
    final verifier = SchemaVerifier(GeneratedHelper());
    final connection = await verifier.startAt(1);
    final database = v1.DatabaseAtV1(connection);

    addTearDown(database.close);

    expect(database.schemaVersion, 1);
    expect(await database.select(database.appMetadata).get(), isEmpty);

    await database
        .into(database.appMetadata)
        .insert(
          v1.AppMetadataCompanion.insert(key: 'snapshot.check', value: 'v1'),
        );

    final rows = await database.select(database.appMetadata).get();

    expect(rows, hasLength(1));
    expect(rows.single.key, 'snapshot.check');
    expect(rows.single.value, 'v1');
  });
}
