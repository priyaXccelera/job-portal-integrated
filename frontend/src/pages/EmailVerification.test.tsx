import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EmailVerification } from './EmailVerification';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <EmailVerification />
    </MemoryRouter>
  );
});
