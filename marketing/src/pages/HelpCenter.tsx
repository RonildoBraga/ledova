import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CaretDown as CaretDownIcon,
  Question as QuestionIcon,
  ArrowRight as ArrowRightIcon,
} from '@phosphor-icons/react';

interface FAQItem {
  question: string;
  answer: string;
}

interface FAQSection {
  title: string;
  items: FAQItem[];
}

const FAQ_SECTIONS: FAQSection[] = [
  {
    title: 'Getting Started',
    items: [
      {
        question: 'What is Ledova?',
        answer:
          'Ledova is an experimental open-source reference project for local development and public-testnet research. It is not a hosted financial service.',
      },
      {
        question: 'Can I use real accounts or identity data?',
        answer:
          'No. Use synthetic data and disposable development credentials. The included signup and identity screens are example interfaces, not an operated verification service.',
      },
      {
        question: 'Which networks are in scope?',
        answer:
          'Local development networks and Base Sepolia are the supported EVM environments. Other chain-related code is experimental and must be configured with test endpoints.',
      },
    ],
  },
  {
    title: 'Security',
    items: [
      {
        question: 'How does Ledova keep my assets safe?',
        answer:
          'It does not make that guarantee. The repository is unaudited and must not be used with real assets, production accounts, or valuable keys.',
      },
      {
        question: 'What is air-gapped signing?',
        answer:
          'Some example flows exchange unsigned and signed transaction data with compatible hardware through QR codes. Review and test the full implementation before relying on it.',
      },
      {
        question: 'Do you store my private keys?',
        answer:
          'The project does not operate a service or store user data. A person running a deployment is responsible for evaluating its key-handling paths and security controls.',
      },
    ],
  },
  {
    title: 'Wallets & Transactions',
    items: [
      {
        question: 'How do I add a wallet?',
        answer:
          'The clients contain example hardware, software, and watch-only wallet flows. Use only disposable test keys and synthetic addresses while evaluating them.',
      },
      {
        question: 'How do I send digital assets?',
        answer:
          'Transaction preparation, signing, and broadcast code is present for development testing. Restrict it to local networks or supported public testnets and use assets with no value.',
      },
      {
        question: 'How long do transactions take?',
        answer:
          'Confirmation time varies by network and conditions. The interface estimates are illustrative and should not be treated as a service commitment.',
      },
    ],
  },
  {
    title: 'Account & Support',
    items: [
      {
        question: 'How do I update my profile?',
        answer:
          'Profile screens are example application code. Use synthetic data, and do not treat the repository as an operated account system.',
      },
      {
        question: 'How do I contact support?',
        answer:
          'This reference repository does not operate a support desk. The owner of a deployment must provide its own support channel.',
      },
      {
        question: 'Is there a mobile app?',
        answer:
          'The repository includes an experimental Expo application for local development and internal test builds. No public app-store release is claimed.',
      },
    ],
  },
];

function AccordionItem({ item }: { item: FAQItem }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="border-b border-border-subtle last:border-b-0">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between py-4 text-left transition-colors hover:text-brand-light"
      >
        <span className="pr-4 text-sm font-medium text-text-primary">{item.question}</span>
        <CaretDownIcon
          size={16}
          weight="bold"
          className={`shrink-0 text-text-muted transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>
      {isOpen && <p className="pb-4 text-sm leading-relaxed text-text-muted">{item.answer}</p>}
    </div>
  );
}

export function HelpCenter() {
  return (
    <>
      <section className="pb-16 pt-24 lg:pt-32">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mx-auto max-w-3xl text-center">
            <div className="mb-6 inline-flex rounded-xl bg-brand/10 p-3">
              <QuestionIcon size={24} weight="duotone" className="text-brand-light" />
            </div>
            <h1 className="text-4xl font-bold text-text-primary sm:text-5xl">Help Centre</h1>
            <p className="mt-4 text-lg text-text-muted">Find answers to common questions about Ledova.</p>
          </div>
        </div>
      </section>

      <section className="border-t border-border-subtle bg-surface-raised/50 py-24">
        <div className="mx-auto max-w-3xl px-6">
          <div className="space-y-8">
            {FAQ_SECTIONS.map((section) => (
              <div
                key={section.title}
                className="rounded-2xl border border-border-subtle bg-surface-base/80 p-6 transition-colors hover:border-border"
              >
                <h2 className="mb-4 text-3xl font-bold text-text-primary">{section.title}</h2>
                <div>
                  {section.items.map((item) => (
                    <AccordionItem key={item.question} item={item} />
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-12 text-center">
            <p className="mb-4 text-text-muted">Still have questions?</p>
            <Link
              to="/contact"
              className="inline-flex items-center gap-2 rounded-xl bg-brand px-8 py-3.5 text-base font-semibold text-white transition-colors hover:bg-brand-hover"
            >
              Contact Support
              <ArrowRightIcon size={18} weight="bold" />
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
