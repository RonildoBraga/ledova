import { Field, Label, Description } from '@headlessui/react';
import type { CheckboxGroupFieldProps } from '@ledova/shared';

const CheckboxGroupField = ({ label, value, options, error, onChange }: CheckboxGroupFieldProps) => {
  const handleCheckboxChange = (optionValue: string, checked: boolean) => {
    if (checked) {
      onChange([...value, optionValue]);
    } else {
      onChange(value.filter((val) => val !== optionValue));
    }
  };

  return (
    <Field className="space-y-3">
      <Label className="block text-sm font-medium text-text-body">
        {label} <span className="text-text-subtle">(select all that apply)</span>
      </Label>
      <div className="grid grid-cols-2 gap-2">
        {options.map((option) => {
          const isChecked = value.includes(option.value);
          return (
            <div
              key={option.value}
              className="flex items-center text-sm text-text-body hover:text-text-primary cursor-pointer"
              onClick={() => handleCheckboxChange(option.value, !isChecked)}
            >
              <div
                className={`h-4 w-4 rounded border ${
                  isChecked ? 'border-brand bg-brand' : 'border-border bg-surface-tertiary'
                } mr-2 flex items-center justify-center cursor-pointer focus:ring-border-focus focus:ring-offset-surface-base`}
                onClick={() => handleCheckboxChange(option.value, !isChecked)}
              >
                {isChecked && (
                  <svg className="h-3 w-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </div>
              {option.label}
            </div>
          );
        })}
      </div>
      {error && (
        <Description className="text-error-light text-sm mt-1" role="alert">
          {error.join(' ')}
        </Description>
      )}
    </Field>
  );
};

export default CheckboxGroupField;
