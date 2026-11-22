import { Navigate, Route, Routes } from "react-router-dom";
import Layout, { RequireAuth } from "./Layout";
import Home from "./pages/Home";
import Login from "./pages/Login";
import ExamsList from "./pages/ExamsList";
import NewExam from "./pages/NewExam";
import SessionsList from "./pages/SessionsList";
import SessionDetail from "./pages/SessionDetail";
import TakeExam from "./pages/TakeExam";
import PendingValidations from "./pages/PendingValidations";
import JoinExam from "./pages/JoinExam";
import Account from "./pages/Account";
import NotFound from "./pages/NotFound";

export default function App() {
  return (
    <Routes>
      {/* Inicio público: elegir entre rendir (estudiante) y el panel docente. */}
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      {/* Ingreso del estudiante con solo el código (evaluación de usabilidad, problema 2). */}
      <Route path="/rendir" element={<JoinExam />} />
      <Route path="/exam" element={<JoinExam />} />
      <Route path="/exam/:joinCode" element={<TakeExam />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/exams" element={<ExamsList />} />
          <Route path="/exams/nueva" element={<NewExam />} />
          <Route path="/exams/:examId" element={<Navigate to="sessions" replace />} />
          <Route path="/exams/:examId/sessions" element={<SessionsList />} />
          <Route path="/sessions/:sessionId" element={<SessionDetail />} />
          <Route path="/validaciones" element={<PendingValidations />} />
          <Route path="/cuenta" element={<Account />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
