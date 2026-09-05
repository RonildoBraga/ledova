import { Field, Label, Description, Radio, RadioGroup } from '@headlessui/react';
import type { RadioGroupFieldProps } from '@ledova/shared';

const RadioGroupField = ({ label, value, options, error, onChange }: RadioGroupFieldProps) => (
  <Field className="space-y-3">
    <Label className="block text-sm font-medium text-text-body">{label}</Label>
    <RadioGroup value={value} onChange={onChange} className="space-y-2">
      {options.map((option) => (
        <Radio
          key={option.value}
          value={option.value}
          className="flex items-center text-sm text-text-body hover:text-text-primary cursor-pointer"
        >
          {({ checked }) => (
            <>
              <div
                className={`h-4 w-4 rounded-full border ${
                  checked ? 'border-brand bg-brand' : 'border-border bg-surface-tertiary'
                } mr-3 flex items-center justify-center focus:ring-border-focus focus:ring-offset-surface-base`}
              >
                {checked && <div className="h-2 w-2 rounded-full bg-white" />}
              </div>
              {option.label}
            </>
          )}
        </Radio>
      ))}
    </RadioGroup>
    {error && (
      <Description className="text-error-light text-sm mt-1" role="alert">
        {error.join(' ')}
      </Description>
    )}
  </Field>
);

export default RadioGroupField;
