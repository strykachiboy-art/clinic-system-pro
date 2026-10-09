import 'package:flutter/material.dart';

import 'package:clinic_system_pro/core/config/backend_config.dart';
import 'package:clinic_system_pro/core/networking/api_client.dart';
import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';
import 'package:clinic_system_pro/features/backend_health/presentation/backend_health_screen.dart';

void main() {
  final apiClient = ApiClient(config: BackendConfig.fromEnvironment());

  final healthDataSource = BackendHealthRemoteDataSource(apiClient: apiClient);

  runApp(ClinicSystemProApp(healthDataSource: healthDataSource));
}

class ClinicSystemProApp extends StatelessWidget {
  const ClinicSystemProApp({super.key, required this.healthDataSource});

  final BackendHealthRemoteDataSource healthDataSource;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Clinic System Pro',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
      ),
      home: BackendHealthScreen(dataSource: healthDataSource),
    );
  }
}
