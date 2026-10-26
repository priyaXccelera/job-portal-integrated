import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MobileOtpVerification } from './MobileOtpVerification';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <MobileOtpVerification />
    </MemoryRouter>
  );
});
