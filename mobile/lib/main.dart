import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:clinic_system_pro/core/config/backend_config.dart';
import 'package:clinic_system_pro/core/networking/api_client.dart';
import 'package:clinic_system_pro/core/routing/app_router.dart';
import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';

void main() {
  final apiClient = ApiClient(config: BackendConfig.fromEnvironment());

  final healthDataSource = BackendHealthRemoteDataSource(apiClient: apiClient);

  runApp(ClinicSystemProApp(healthDataSource: healthDataSource));
}

class ClinicSystemProApp extends StatefulWidget {
  const ClinicSystemProApp({super.key, required this.healthDataSource});

  final BackendHealthRemoteDataSource healthDataSource;

  @override
  State<ClinicSystemProApp> createState() => _ClinicSystemProAppState();
}

class _ClinicSystemProAppState extends State<ClinicSystemProApp> {
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _router = createAppRouter(
      healthDataSource: widget.healthDataSource,
    );
  }

  @override
  void dispose() {
    _router.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Clinic System Pro',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
      ),
      routerConfig: _router,
    );
  }
}
