import { Navigate, Route, Routes } from "react-router-dom";
import AdminGuard from "./components/AdminGuard";
import AdminLayout from "./components/AdminLayout";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Overview from "./pages/admin/Overview";
import UserDetail from "./pages/admin/UserDetail";
import Users from "./pages/admin/Users";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/signup" replace />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/login" element={<Login />} />
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
      <Route path="*" element={<Navigate to="/signup" replace />} />
    </Routes>
  );
}
