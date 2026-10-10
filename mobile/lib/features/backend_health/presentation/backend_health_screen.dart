import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';
import 'package:clinic_system_pro/features/backend_health/presentation/backend_health_cubit.dart';

class BackendHealthScreen extends StatelessWidget {
  const BackendHealthScreen({super.key, required this.dataSource});

  final BackendHealthRemoteDataSource dataSource;

  @override
  Widget build(BuildContext context) {
    return BlocProvider<BackendHealthCubit>(
      create: (_) {
        final cubit = BackendHealthCubit(dataSource: dataSource);
        unawaited(cubit.checkHealth());
        return cubit;
      },
      child: const _BackendHealthView(),
    );
  }
}

class _BackendHealthView extends StatelessWidget {
  const _BackendHealthView();

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<BackendHealthCubit, BackendHealthState>(
      builder: (context, state) {
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
                        _buildStatus(context, state),
                        const SizedBox(height: 24),
                        SizedBox(
                          width: double.infinity,
                          child: ElevatedButton.icon(
                            onPressed:
                                state.status == BackendHealthStatus.checking
                                ? null
                                : () => unawaited(
                                    context
                                        .read<BackendHealthCubit>()
                                        .checkHealth(),
                                  ),
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
      },
    );
  }

  Widget _buildStatus(BuildContext context, BackendHealthState state) {
    final colors = Theme.of(context).colorScheme;

    switch (state.status) {
      case BackendHealthStatus.checking:
        return const Column(
          children: [
            CircularProgressIndicator(key: ValueKey('backend-health-loading')),
            SizedBox(height: 16),
            Text('Checking GET /health/live...'),
          ],
        );

      case BackendHealthStatus.healthy:
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

      case BackendHealthStatus.unhealthy:
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

      case BackendHealthStatus.unavailable:
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
              state.errorMessage ?? 'Unable to check the backend.',
              textAlign: TextAlign.center,
            ),
          ],
        );
    }
  }
}
