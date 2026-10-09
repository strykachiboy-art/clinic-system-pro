import 'package:clinic_system_pro/core/networking/api_client.dart';

/// Reads the liveness status from the existing Flask backend.
class BackendHealthRemoteDataSource {
  const BackendHealthRemoteDataSource({required this.apiClient});
  final ApiClient apiClient;

  /// Returns true only for the documented healthy liveness response.
  Future<bool> checkLiveness() async {
    final response = await apiClient.getJson('health/live');

    return response['success'] == true && response['status'] == 'ok';
  }
}
