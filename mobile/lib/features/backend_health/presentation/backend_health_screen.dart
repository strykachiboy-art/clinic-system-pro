import 'dart:async';

import 'package:flutter/material.dart';
import 'package:clinic_system_pro/core/networking/api_exception.dart';
import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';

enum _HealthCheckState { checking, healthy, unhealthy, unavailable }

class BackendHealthScreen extends StatefulWidget {
  const BackendHealthScreen({super.key, required this.dataSource});

  final BackendHealthRemoteDataSource dataSource;

  @override
  State<BackendHealthScreen> createState() => _BackendHealthScreenState();
}

class _BackendHealthScreenState extends State<BackendHealthScreen> {
  _HealthCheckState _state = _HealthCheckState.checking;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    unawaited(_checkHealth());
  }

  Future<void> _checkHealth() async {
    if (_state != _HealthCheckState.checking || _errorMessage != null) {
      setState(() {
        _state = _HealthCheckState.checking;
        _errorMessage = null;
      });
    }

    try {
      final healthy = await widget.dataSource.checkLiveness();

      if (!mounted) return;

      setState(() {
        _state = healthy
            ? _HealthCheckState.healthy
            : _HealthCheckState.unhealthy;
      });
    } on ApiException catch (error) {
      if (!mounted) return;

      setState(() {
        _state = _HealthCheckState.unavailable;
        _errorMessage = error.message;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        _state = _HealthCheckState.unavailable;
        _errorMessage =
            'An unexpected error occurred while checking the backend.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Backend connectivity')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.cloud_outlined,
                      size: 48,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Clinic System Pro',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 24),
                    _buildStatus(context),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: _state == _HealthCheckState.checking
                            ? null
                            : _checkHealth,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Check again'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStatus(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    switch (_state) {
      case _HealthCheckState.checking:
        return const Column(
          children: [
            CircularProgressIndicator(key: ValueKey('backend-health-loading')),
            SizedBox(height: 16),
            Text('Checking GET /health/live...'),
          ],
        );

      case _HealthCheckState.healthy:
        return Column(
          children: [
            Icon(Icons.check_circle_outline, size: 48, color: colors.primary),
            const SizedBox(height: 12),
            Text(
              'Backend reachable',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            const Text('GET /health/live returned the expected response.'),
          ],
        );

      case _HealthCheckState.unhealthy:
        return Column(
          children: [
            Icon(Icons.warning_amber_rounded, size: 48, color: colors.error),
            const SizedBox(height: 12),
            Text(
              'Unexpected health response',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            const Text(
              'The backend responded, but its liveness status was not ok.',
              textAlign: TextAlign.center,
            ),
          ],
        );

      case _HealthCheckState.unavailable:
        return Column(
          children: [
            Icon(Icons.cloud_off_outlined, size: 48, color: colors.error),
            const SizedBox(height: 12),
            Text(
              'Backend unavailable',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              _errorMessage ?? 'Unable to check the backend.',
              textAlign: TextAlign.center,
            ),
          ],
        );
    }
  }
}
