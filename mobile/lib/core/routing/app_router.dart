import 'package:go_router/go_router.dart';

import 'package:clinic_system_pro/features/backend_health/data/backend_health_remote_data_source.dart';
import 'package:clinic_system_pro/features/backend_health/presentation/backend_health_screen.dart';

GoRouter createAppRouter({
  required BackendHealthRemoteDataSource healthDataSource,
}) {
  return GoRouter(
    initialLocation: '/health',
    routes: [
      GoRoute(
        path: '/health',
        name: 'health',
        builder: (context, state) {
          return BackendHealthScreen(dataSource: healthDataSource);
        },
      ),
    ],
  );
}
