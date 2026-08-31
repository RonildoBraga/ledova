export interface Country {
  uuid: string;
  name: string;
  code: string;
  dialCode: string | null;
  isAvailable: boolean;
}
