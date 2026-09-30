from app.modules.dashboard.schemas.dashboard_schema import (
    DashboardActivitySchema,
    DashboardAlertSchema,
    DashboardChatSummarySchema,
    DashboardContextSchema,
    DashboardMetricSchema,
    DashboardPeriodSchema,
    DashboardQuerySchema,
    DashboardTrendSchema,
)

from app.modules.dashboard.schemas.super_admin_dashboard_schema import (
    SuperAdminAccessControlOverviewSchema,
    SuperAdminAIDashboardSchema,
    SuperAdminAIApprovalSummarySchema,
    SuperAdminAIFeatureUsageSchema,
    SuperAdminAIOverviewSchema,
    SuperAdminAIRiskSummarySchema,
    SuperAdminDashboardOverviewSchema,
    SuperAdminDashboardSchema,
)

from app.modules.dashboard.schemas.management_dashboard_schema import (
    ManagementAIDashboardSchema,
    ManagementAIApprovalSummarySchema,
    ManagementAIFeatureUsageSchema,
    ManagementAIOverviewSchema,
    ManagementAIRiskSummarySchema,
    ManagementDashboardOverviewSchema,
    ManagementDashboardSchema,
)

from app.modules.dashboard.schemas.clinical_dashboard_schema import (
    ClinicalAIDashboardSchema,
    ClinicalAIOverviewSchema,
    ClinicalAIFeatureUsageSchema,
    ClinicalAIReviewSummarySchema,
    ClinicalAIRiskSummarySchema,
    ClinicalDashboardOverviewSchema,
    ClinicalDashboardSchema,
)

from app.modules.dashboard.schemas.operations_dashboard_schema import (
    OperationsDashboardOverviewSchema,
    OperationsDashboardSchema,
)

from app.modules.dashboard.schemas.finance_dashboard_schema import (
    FinanceAICostSchema,
    FinanceDashboardOverviewSchema,
    FinanceDashboardSchema,
)

from app.modules.dashboard.schemas.patient_dashboard_schema import (
    PatientDashboardOverviewSchema,
    PatientDashboardSchema,
)

__all__ = [
    "DashboardActivitySchema",
    "DashboardAlertSchema",
    "DashboardChatSummarySchema",
    "DashboardContextSchema",
    "DashboardMetricSchema",
    "DashboardPeriodSchema",
    "DashboardQuerySchema",
    "DashboardTrendSchema",

    "SuperAdminAccessControlOverviewSchema",
    "SuperAdminAIDashboardSchema",
    "SuperAdminAIApprovalSummarySchema",
    "SuperAdminAIFeatureUsageSchema",
    "SuperAdminAIOverviewSchema",
    "SuperAdminAIRiskSummarySchema",
    "SuperAdminDashboardOverviewSchema",
    "SuperAdminDashboardSchema",

    "ManagementAIDashboardSchema",
    "ManagementAIApprovalSummarySchema",
    "ManagementAIFeatureUsageSchema",
    "ManagementAIOverviewSchema",
    "ManagementAIRiskSummarySchema",
    "ManagementDashboardOverviewSchema",
    "ManagementDashboardSchema",

    "ClinicalAIDashboardSchema",
    "ClinicalAIOverviewSchema",
    "ClinicalAIFeatureUsageSchema",
    "ClinicalAIReviewSummarySchema",
    "ClinicalAIRiskSummarySchema",
    "ClinicalDashboardOverviewSchema",
    "ClinicalDashboardSchema",

    "OperationsDashboardOverviewSchema",
    "OperationsDashboardSchema",

    "FinanceAICostSchema",
    "FinanceDashboardOverviewSchema",
    "FinanceDashboardSchema",

    "PatientDashboardOverviewSchema",
    "PatientDashboardSchema",
]