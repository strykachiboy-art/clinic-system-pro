import 'package:flutter/material.dart';

void main() {
  runApp(const ClinicSystemProApp());
}

class ClinicSystemProApp extends StatelessWidget {
  const ClinicSystemProApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Clinic System Pro',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.teal,
        ),
      ),
      home: Scaffold(
        appBar: AppBar(
          title: Text('Clinic System Pro'),
        ),
        body: Center(
          child: Text('Clinic System Pro mobile foundation'),
        ),
      ),
    );
  }
}