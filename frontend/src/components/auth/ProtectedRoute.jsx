import { Navigate } from "react-router-dom";
import { useAuth } from "../../api/useAuth";

export default function ProtectedRoute({ children, requiredRole }) {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole) {
    const roles = Array.isArray(requiredRole) ? requiredRole : [requiredRole];
    if (!roles.includes(user.role)) {
      return (
        <div className="flex-1 flex items-center justify-center bg-gray-900 text-red-400">
          <div className="text-center">
            <p className="text-lg font-semibold">Access Denied</p>
            <p className="text-sm text-gray-500 mt-1">
              You don't have permission to view this page
            </p>
          </div>
        </div>
      );
    }
  }

  return children;
}
