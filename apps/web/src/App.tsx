import { Navigate, Route, Routes } from "react-router-dom";
import AdminGuard from "./components/AdminGuard";
import AdminLayout from "./components/AdminLayout";
import AppLayout from "./components/AppLayout";
import AuthGuard from "./components/AuthGuard";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import HomeRedirect from "./pages/HomeRedirect";
import Dashboard from "./pages/Dashboard";
import Overview from "./pages/admin/Overview";
import UserDetail from "./pages/admin/UserDetail";
import Users from "./pages/admin/Users";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="/app"
        element={
          <AuthGuard>
            <AppLayout />
          </AuthGuard>
        }
      >
        <Route index element={<Dashboard />} />
      </Route>
      <Route
        path="/admin"
        element={
          <AdminGuard>
            <AdminLayout />
          </AdminGuard>
        }
      >
        <Route index element={<Overview />} />
        <Route path="users" element={<Users />} />
        <Route path="users/:id" element={<UserDetail />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
