import ButtonGroup from "react-bootstrap/ButtonGroup";
import ToggleButton from "react-bootstrap/ToggleButton";

const ROLES = [
  { value: "student", label: "Student" },
  { value: "company", label: "Company" },
];

// The Student / Company switch used on the login and signup forms.
export default function RoleToggle({ value, onChange, disabled = false }) {
  return (
    <ButtonGroup className="w-100 mb-3" aria-label="Account type">
      {ROLES.map((role) => (
        <ToggleButton
          key={role.value}
          id={`role-${role.value}`}
          type="radio"
          name="role"
          variant={value === role.value ? "primary" : "outline-primary"}
          value={role.value}
          checked={value === role.value}
          disabled={disabled}
          onChange={() => onChange(role.value)}
        >
          {role.label}
        </ToggleButton>
      ))}
    </ButtonGroup>
  );
}
