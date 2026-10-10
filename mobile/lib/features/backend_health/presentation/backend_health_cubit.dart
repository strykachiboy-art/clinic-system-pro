import 'package:flutter_bloc/flutter_bloc.dart';

import 'package:clinic_system_pro/core/networking/api_exception.dart';
import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';

enum BackendHealthStatus { checking, healthy, unhealthy, unavailable }

class BackendHealthState {
  const BackendHealthState({
    required this.status,
    this.errorMessage,
  });

  final BackendHealthStatus status;
  final String? errorMessage;
}

class BackendHealthCubit extends Cubit<BackendHealthState> {
  BackendHealthCubit({
    required this.dataSource,
  }) : super(const BackendHealthState(status: BackendHealthStatus.checking));

  final BackendHealthRemoteDataSource dataSource;
  bool _requestInProgress = false;

  Future<void> checkHealth() async {
    if (_requestInProgress || isClosed) return;

    _requestInProgress = true;
    emit(const BackendHealthState(status: BackendHealthStatus.checking));

    try {
      final healthy = await dataSource.checkLiveness();

      if (isClosed) return;

      emit(
        BackendHealthState(
          status: healthy
              ? BackendHealthStatus.healthy
              : BackendHealthStatus.unhealthy,
        ),
      );
    } on ApiException catch (error) {
      if (isClosed) return;

      emit(
        BackendHealthState(
          status: BackendHealthStatus.unavailable,
          errorMessage: error.message,
        ),
      );
    } catch (_) {
      if (isClosed) return;

      emit(
        const BackendHealthState(
          status: BackendHealthStatus.unavailable,
          errorMessage:
              'An unexpected error occurred while checking the backend.',
        ),
      );
    } finally {
      _requestInProgress = false;
    }
  }
}
