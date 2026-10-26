import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MessagesInbox } from './MessagesInbox';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <MessagesInbox />
    </MemoryRouter>
  );
});
