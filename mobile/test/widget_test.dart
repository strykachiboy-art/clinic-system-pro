import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_system_pro/main.dart';

void main() {
  testWidgets(
    'Clinic System Pro foundation app renders',
    (WidgetTester tester) async {
      await tester.pumpWidget(const ClinicSystemProApp());

      expect(
        find.text('Clinic System Pro mobile foundation'),
        findsOneWidget,
      );

      expect(
        find.text('Clinic System Pro'),
        findsOneWidget,
      );
    },
  );
}